# This file is part of ts_MTAlignment.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["AlignmentCSC", "run_mtalignment"]

import asyncio
import typing
import pathlib

from lsst.ts import salobj

from . import __version__
from .alignment_model import AlignmentModel
from .utils import parse_offsets, parse_single_point_measurement, Target
from .config_schema import CONFIG_SCHEMA


# The following targets must appear in config.targets
REQUIRED_TARGETS = {"CAM", "M1M3", "M2"}


class AlignmentCSC(salobj.ConfigurableCsc):
    """CSC to control the MT alignment measurement system.

    Parameters
    ----------
    config_dir : `str` (optional)
        Directory of configuration files, or None for the standard
        configuration directory (obtained from `get_default_config_dir`).
        This is provided for unit testing.
    initial_state : `salobj.State` (optional)
        The initial state of the CSC. Typically one of:
        - State.ENABLED if you want the CSC immediately usable.
        - State.STANDBY if you want full emulation of a CSC.
    override : `str`, optional
        Configuration override file to apply if ``initial_state`` is
        `State.DISABLED` or `State.ENABLED`.
    simulation_mode : `int`, optional
        Simulation mode; one of:

        * 0: normal operation
        * 1: use the simulation features of SpatialAnalyzer
        * 2: minimal internal simulator with canned responses
    """

    version: str = __version__
    valid_simulation_modes: typing.Tuple[int, int, int] = (0, 1, 2)
    simulation_help: str = """
    Simulation mode 1 does not fully simulate the CSC, but rather
    taps into the simulation features of SpatialAnalyzer. This should allow
    us to exercise the vendor code in tests and also a very robust simulation
    of actual alignment operations, but it means simulation mode 1 still
    relies on being able to make a TCP connection to the vendor provided T2SA
    application, which must be hosted on a Windows machine or VM with a
    licensed copy of SpatialAnalyzer.

    Simulation mode 2 can be run locally without T2SA, but it only accepts
    connections and then acts as a glorified dictionary that returns a few
    canned responses.
    """

    def __init__(
        self,
        config_dir: typing.Union[str, pathlib.Path, None] = None,
        initial_state: salobj.State = salobj.State.STANDBY,
        override: str = "",
        simulation_mode: int = 0,
    ) -> None:
        super().__init__(
            name="MTAlignment",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )
        self.model: typing.Union[None, AlignmentModel] = None
        self.max_iters = 3

        # These values are only used to tag the data on the T2SA and do not
        # need to have any connection with the actual telescope position.
        # Will set some default values were we plan to execute the measurements
        # we could make these configurable parameters, or even add a command
        # to allow dynamic changing them, but I am not confident this is
        # necessary.
        self.elevation = 60
        self.azimuth = 0
        self.camrot = 0

        self.last_measurement: typing.Union[
            dict[str, typing.Union[float, str]], None
        ] = None

        self.telemetry_loop_task: typing.Union[None, asyncio.Task] = None
        self.laser_status_ready = asyncio.Event()

    async def handle_summary_state(self) -> None:
        """Override parentclass method to handle summary state changes."""
        if self.disabled_or_enabled:
            if self.model is None:
                self.model = AlignmentModel(
                    domain=self.domain,
                    host=self.config.t2sa_host,
                    port=self.config.t2sa_port,
                    read_timeout=self.config.read_timeout,
                    simulation_mode=self.simulation_mode,
                    log=self.log,
                )
                await self.model.connect()
                self.log.debug(
                    f"connected to t2sa at {self.model.host}:{self.model.port}"
                )

            if self.telemetry_loop_task is None:
                self.telemetry_loop_task = asyncio.create_task(
                    self.run_telemetry_loop()
                )
        else:
            if self.model is not None:
                await self.model.disconnect()
                self.model = None

            if self.telemetry_loop_task is not None:
                await self.reset_telemetry_loop()

    async def configure(self, config: typing.Any) -> None:
        """Override parentclass method to configure CSC.

        Parameters
        ----------
        config : `object`
            The configuration, as described by the config schema, as a
            struct-like object.
        """
        missing_targets = REQUIRED_TARGETS - set(config.targets)
        if missing_targets:
            raise RuntimeError(
                f"config.targets is missing required targets {sorted(missing_targets)}"
            )
        self.config = config
        if self.model is not None:
            if self.model.connected:
                await self.model.disconnect()
            await self.model.connect()

    @staticmethod
    def get_config_pkg() -> str:
        return "ts_config_mttcs"

    async def do_measureTarget(self, data: salobj.BaseDdsDataType) -> None:
        """Measure and return coordinates of a target.

        Parameters
        ----------
        data : ``cmd_measureTarget.DataType``
            Command data.
        """
        self.log.debug("measure Target")
        self.assert_enabled()
        assert self.model is not None
        if data.target not in self.config.targets:
            raise salobj.ExpectedError(
                f"Unknown target {data.target}; must one of {self.config.targets}"
            )

        self.laser_status_ready.clear()
        await self.model.measure_target(data.target)
        await self.laser_status_ready.wait()

        result = await self.model.get_target_position(data.target)

        self.last_measurement = parse_offsets(result)
        await self.evt_positionPublish.set_write(**self.last_measurement)

    async def do_align(self, data: salobj.BaseDdsDataType) -> None:
        """Perform correction loop.

        Parameters
        ----------
        data : ``cmd_align.DataType``
            Command data.
        """
        self.assert_enabled()

        target = Target(data.target)

        await self.correction_loop(target=target.name)

    async def do_healthCheck(self, data: salobj.BaseDdsDataType) -> None:
        """Execute healthcheck.

        Parameters
        ----------
        data : ``cmd_healthcheck.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None

        self.log.info("Running health check.")
        for target in self.config.targets:
            self.log.debug(f"Running two face check for {target}.")
            await self.model.twoface_check(target)
            self.log.debug(f"Measuring drift for {target}.")
            await self.model.measure_drift(target)

    async def do_laserPower(self, data: salobj.BaseDdsDataType) -> None:
        """Power laser on/off.

        Parameters
        ----------
        data : ``cmd_laserPower``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        if data.power == 0:
            await self.model.laser_off()
        else:
            await self.model.laser_on()

    async def do_powerOff(self, data: salobj.BaseDdsDataType) -> None:
        """Fully power off tracker and interface.

        This requires a manual startup after being executed.

        Parameters
        ----------
        data : ``cmd_powerOff.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        await self.model.tracker_off()

    async def do_measurePoint(self, data: salobj.BaseDdsDataType) -> None:
        """Measure and return coords of a specific point.

        Parameters
        ----------
        data : ``cmd_measuerPoint.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        single_point_measurement = await self.model.measure_single_point(
            data.collection, data.pointgroup, data.target
        )

        measurement = parse_single_point_measurement(single_point_measurement)

        if measurement is None:
            raise RuntimeError(
                f"Failed to parse single point measurement: {single_point_measurement}"
            )

        self.log.debug(single_point_measurement)

        await self.evt_positionPublish.set_write(
            target=f"{data.target}",
            dX=measurement.x,
            dY=measurement.y,
            dZ=measurement.z,
            dRX=0.0,
            dRY=0.0,
            dRZ=0.0,
        )

    async def do_pointDelta(self, data: salobj.BaseDdsDataType) -> None:
        """Publish an event containing a vector between two points.

        Parameters
        ----------
        data : ``cmd_pointDelta.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        point_delta = await self.model.get_point_delta(
            p1collection=data.collection_A,
            p1group=data.pointgroup_A,
            p1=data.target_A,
            p2group=data.pointgroup_B,
            p2=data.target_B,
            p2collection=data.collection_B,
        )

        self.log.debug(f"Point delta: {point_delta}.")
        # TODO: Publish event

    async def do_setReferenceGroup(self, data: salobj.BaseDdsDataType) -> None:
        """Set the reference group with respect to which all measumentes will
        be made against.

        Parameters
        ----------
        data : ``cmd_setReferenceGroup.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        await self.model.set_reference_group(data.referenceGroup)

        # TODO: Publish reference group

    async def do_setWorkingFrame(self, data: salobj.BaseDdsDataType) -> None:
        """Set the SpatialAnalyzer working frame.

        Parameters
        ----------
        data : ``cmd_setWorkingFrame.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        await self.model.set_working_frame(data.workingFrame)

        # TODO: Publish an event with the working frame.

    async def do_halt(self, data: salobj.BaseDdsDataType) -> None:
        """Halts any executing measurement plan and returns to ready state.

        Parameters
        ----------
        data : ``cmd_halt.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        await self.model.halt()

    async def do_loadSATemplateFile(self, data: salobj.BaseDdsDataType) -> None:
        """Load SA Template file.

        Parameters
        ----------
        data : ``cmd_loadSATemplateFile.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        await self.model.load_template_file(data.file)

        # TODO: Publish something?

    async def do_measureDrift(self, data: salobj.BaseDdsDataType) -> None:
        """Measure tracker drift.

        Parameters
        ----------
        data : ``cmd_measureDrift.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        await self.model.measure_drift(data.pointgroup)

        # TODO: Publish something?

    async def do_resetT2SA(self, data: salobj.BaseDdsDataType) -> None:
        """Reboots t2sa and SA.

        Parameters
        ----------
        data : ``cmd_resetT2SA.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None

        await self.model.reset_t2sa()

        # TODO: Publish something?

    async def do_newStation(self, data: salobj.BaseDdsDataType) -> None:
        """Add new tracker station.

        Parameters
        ----------
        data : ``cmd_newStation.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None

        await self.model.new_station()

        # TODO: Publish something?

    async def do_saveJobfile(self, data: salobj.BaseDdsDataType) -> None:
        """Save job file.

        Parameters
        ----------
        data : ``cmd_saveJobFile.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None

        await self.model.save_sa_jobfile(data.file)

        # TODO: Publish something?

    async def correction_loop(self, target: str) -> None:
        """Measure the offset between M1M3 optimum position and the target.

        Parameters
        ----------
        target : `str`
            Target to measure offset with respect to M1M3 optimum position.
        """

        assert self.model is not None

        await self.model.set_telescope_position(
            telalt=self.elevation,
            telaz=self.azimuth,
            camrot=self.camrot,
        )

        await self.model.measure_target("M1M3")

        if target != "M1M3":
            await self.model.measure_target(target)

        target_offset_str = await self.model.get_target_offset(
            target=target, reference_pointgroup="M1M3"
        )
        target_offset = parse_offsets(target_offset_str)

        if target_offset is None:
            raise RuntimeError(
                f"Failed to parse offsets for {target}: {target_offset_str}"
            )

        await self.evt_offsetsPublish.set_write(**target_offset)

    async def run_telemetry_loop(self) -> None:
        """Run telemetry loop."""

        assert self.model is not None

        while self.disabled_or_enabled:

            status = await self.model.check_status()
            if status == "READY":
                self.laser_status_ready.set()
            else:
                self.laser_status_ready.clear()

            # TODO: Publish events with telemetry data.

            await asyncio.sleep(self.heartbeat_interval)

    async def reset_telemetry_loop(self) -> None:
        """Reset telemetry loop."""

        if self.telemetry_loop_task is not None and not self.telemetry_loop_task.done():
            self.log.debug(
                f"Telemetry loop task still running. Waiting {self.heartbeat_interval}s for it to finish."
            )
            try:
                await asyncio.wait_for(
                    self.telemetry_loop_task, timeout=self.heartbeat_interval
                )
            except asyncio.TimeoutError:
                # TimeoutError might happen if the tasks takes too long to
                # finish. Will cancel it and move forward.
                self.log.debug("Telemetry loop did not finished, cancelling it.")
                self.telemetry_loop_task.cancel()
                try:
                    await self.telemetry_loop_task
                except asyncio.CancelledError:
                    # CancelledError is expected since we canceled it.
                    pass
                except Exception:
                    # Any other exception is unexpected. Will log and continue.
                    self.log.exception("Error cancelling telemetry loop. Ignoring...")
            except Exception:
                # Any other exception is unexpected. Will log and continue.
                self.log.exception("Error finalizing telemetry. Ignoring...")

        self.telemetry_loop_task = None

    def in_tolerance(self, coords: dict[str, typing.Union[str, float]]) -> bool:
        """Returns true if the specified coords are in tolerance.

        Parameters
        ----------
        coords : `Dict`
            Dict containing coordinates
        """
        raise NotImplementedError()


def run_mtalignment() -> None:
    """Run the MTAlignment CSC."""
    asyncio.run(AlignmentCSC.amain(index=None))
