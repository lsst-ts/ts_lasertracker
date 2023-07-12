# This file is part of ts_lasertracker.
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

__all__ = ["LaserTrackerCsc", "run_lasertracker"]

import asyncio
import pathlib
import types
import typing

from lsst.ts import salobj, utils
from lsst.ts.idl.enums.LaserTracker import LaserStatus, SalIndex, T2SAStatus

from . import __version__
from .config_schema import CONFIG_SCHEMA
from .mock import MockT2SA
from .t2sa_model import T2SAModel
from .utils import Target

# The following targets must appear in config.targets
REQUIRED_TARGETS = {"CAM", "M1M3", "M2"}


class LaserTrackerCsc(salobj.ConfigurableCsc):
    """CSC to control the MT alignment measurement system.

    Parameters
    ----------
    index : `SalIndex` or `int`
        SAL index; see `SalIndex` for the allowed values.
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
    valid_simulation_modes: tuple[int, int, int] = (0, 1, 2)
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
        index: SalIndex | int,
        config_dir: str | pathlib.Path | None = None,
        initial_state: salobj.State = salobj.State.STANDBY,
        override: str = "",
        simulation_mode: int = 0,
    ) -> None:
        super().__init__(
            name="LaserTracker",
            index=index,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )
        self.model: None | T2SAModel = None

        # These values are only used to tag the data on the T2SA and do not
        # need to have any connection with the actual telescope position.
        # Will set some default values were we plan to execute the measurements
        # we could make these configurable parameters, or even add a command
        # to allow dynamic changing them, but I am not confident this is
        # necessary.
        self.elevation = 60
        self.azimuth = 0
        self.camrot = 0
        self.elevation_default = 60
        self.azimuth_default = 0
        self.camrot_default = 0
        self.group_idx = 1

        self.timeout_std = 5.0

        self.last_measurement: dict[str, float | str] | None = None

        self._run_telemetry_loop = False
        self.telemetry_loop_task: asyncio.Task = utils.make_done_future()

        self.laser_status_ready = asyncio.Event()

        self._mock_t2sa: None | MockT2SA = None

        self.mtmount_remote = salobj.Remote(
            domain=self.domain,
            name="MTMount",
            readonly=True,
            include=["elevation", "azimuth"],
        )

        self.mtrotator_remote = salobj.Remote(
            domain=self.domain,
            name="MTRotator",
            readonly=True,
            include=["rotation"],
        )

    async def handle_summary_state(self) -> None:
        """Override parent class method to handle summary state changes."""
        if self.disabled_or_enabled:
            t2sa_host = self.config.t2sa_host
            t2sa_port = self.config.t2sa_port

            if self.simulation_mode == 2 and self._mock_t2sa is None:
                self.log.debug("Running t2sa mock.")
                self._mock_t2sa = MockT2SA(log=self.log)
                await self._mock_t2sa.start_task
                t2sa_host = self._mock_t2sa.host
                t2sa_port = self._mock_t2sa.port

            if self.model is None:
                self.log.info(
                    f"Connecting alignment model to: {t2sa_host}:{t2sa_port}, "
                    f"read_timeout={self.config.read_timeout}s [mode: {self.simulation_mode}]."
                )
                self.model = T2SAModel(
                    host=t2sa_host,
                    port=t2sa_port,
                    read_timeout=self.config.read_timeout,
                    t2sa_simulation_mode=self.simulation_mode == 1,
                    log=self.log,
                )
                await self.model.connect()
                self.log.debug(
                    f"Connected to t2sa at {self.model.host}:{self.model.port}. "
                    "Setting telescope position."
                )

            if self.telemetry_loop_task.done():
                self._run_telemetry_loop = True
                self.telemetry_loop_task = asyncio.create_task(
                    self.run_telemetry_loop()
                )
        else:
            await self.stop_telemetry_loop()

            if self.model is not None:
                try:
                    await self.model.disconnect()
                except Exception:
                    self.log.exception("Error disconnecting model. Continuing.")
                self.model = None

            if self._mock_t2sa is not None:
                try:
                    await self._mock_t2sa.close_client()
                    await self._mock_t2sa.close()
                except Exception:
                    self.log.exception("Error closing mock t2sa. Continuing.")
                self._mock_t2sa = None

    async def configure(self, config: typing.Any) -> None:
        """Override parent class method to configure CSC.

        Parameters
        ----------
        config : `object`
            The configuration, as described by the config schema, as a
            struct-like object.
        """
        instance_dicts = [
            instance_dict
            for instance_dict in config.instances
            if instance_dict["sal_index"] == self.salinfo.index
        ]
        if len(instance_dicts) > 1:
            raise salobj.ExpectedError(
                f"Duplicate config entries found for sal_index={self.salinfo.index}"
            )
        elif len(instance_dicts) == 0:
            raise salobj.ExpectedError(
                f"No config found for sal_index={self.salinfo.index}"
            )

        instance = types.SimpleNamespace(**instance_dicts[0])
        missing_targets = REQUIRED_TARGETS - set(instance.targets)
        if missing_targets:
            raise RuntimeError(
                f"config.targets is missing required targets {sorted(missing_targets)}"
            )
        self.config = instance
        self.log.info(f"Configuration: {self.config}")
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

        await self.cmd_measureTarget.ack_in_progress(
            data,
            timeout=self.model.read_timeout,
            result=f"Measuring {data.target}.",
        )

        await self.set_telescope_position()

        self.log.info(f"Measuring target {data.target}.")
        await self.model.measure_target(data.target)

        await self.cmd_measureTarget.ack_in_progress(
            data,
            timeout=self.model.read_timeout,
            result="Get target position.",
        )

        self.log.info("Measurement completed. Publishing target position.")

        target_name = self.get_target_name(data.target)

        self.last_measurement = await self.model.get_target_position(target_name)

        await self.evt_positionPublish.set_write(**self.last_measurement)

    def get_target_name(self, target: str) -> str:
        """Return target frame name from target name.

        Parameters
        ----------
        target : `str`
            Target name.

        Returns
        -------
        target_name : `str`
            Target frame name.
        """
        return (
            f"Meas_{target}_"
            f"{self.elevation:.2f}_"
            f"{self.azimuth:.2f}_"
            f"{self.camrot:.2f}"
            f"{self.group_idx}::"
            f"Frame{target}_"
            f"{self.elevation:.2f}_"
            f"{self.azimuth:.2f}_"
            f"{self.camrot:.2f}"
            f"{self.group_idx}"
        )

    async def do_align(self, data: salobj.BaseDdsDataType) -> None:
        """Measure alignment.

        Parameters
        ----------
        data : ``cmd_align.DataType``
            Command data.
        """
        self.assert_enabled()

        target = Target(data.target)

        await self.measure_alignment(target=target.name)

    async def do_healthCheck(self, data: salobj.BaseDdsDataType) -> None:
        """Execute health check.

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

        .. deprecated:: 0.3.0
            `do_powerOff` is not supported and will be removed in xml 12.1.
        """
        self.assert_enabled()

        # TODO (DM-36112): Remove powerOff command.
        raise salobj.ExpectedError(
            "Powering off the T2SA controller is unsupported from the CSC."
        )

    async def do_measurePoint(self, data: salobj.BaseDdsDataType) -> None:
        """Measure and return coords of a specific point.

        Parameters
        ----------
        data : ``cmd_measuerPoint.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None

        measurement = await self.model.measure_single_point(
            data.collection, data.pointgroup, data.target
        )

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

        # TODO (DM-36112): Publish event and remove log message.
        self.log.info(f"Point delta: {point_delta}.")

    async def do_setReferenceGroup(self, data: salobj.BaseDdsDataType) -> None:
        """Set the reference group with respect to which all measurements will
        be made against.

        Parameters
        ----------
        data : ``cmd_setReferenceGroup.DataType``
            Command data.
        """
        self.assert_enabled()
        assert self.model is not None
        await self.model.set_reference_group(data.referenceGroup)

        # TODO (DM-36112): Publish reference group
        self.log.info(f"New reference group: {data.referenceGroup}")

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

        # TODO (DM-36112): Publish an event with the working frame.

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

        # TODO (DM-36112): Publish something?

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

        # TODO (DM-36112): Publish something?

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

        # TODO (DM-36112): Publish something?

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

        # TODO (DM-36112): Publish something?

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

        # TODO (DM-36112): Publish something?

    async def measure_alignment(self, target: str) -> None:
        """Measure the offset between M1M3 optimum position and the target.

        Parameters
        ----------
        target : `str`
            Target to measure offset with respect to M1M3 optimum position.
        """

        assert self.model is not None

        await self.set_telescope_position()

        await self.model.measure_target("M1M3")

        if target != "M1M3":
            await self.model.measure_target(target)

        target_offset = await self.model.get_target_offset(
            target=target, reference_pointgroup="M1M3"
        )

        await self.evt_offsetsPublish.set_write(**target_offset)

    async def set_telescope_position(self) -> None:
        """Set the telescope positions by retrieving values from the mtmount
        telemetry.
        """
        assert self.model is not None

        elevation_data, azimuth_data, rotator_data = await asyncio.gather(
            self.mtmount_remote.tel_elevation.next(
                flush=True, timeout=self.timeout_std
            ),
            self.mtmount_remote.tel_azimuth.next(flush=True, timeout=self.timeout_std),
            self.mtrotator_remote.tel_rotation.next(
                flush=True, timeout=self.timeout_std
            ),
            return_exceptions=True,
        )

        self.elevation = (
            round(elevation_data.actualPosition, ndigits=2)
            if not isinstance(elevation_data, Exception)
            else self.elevation_default
        )
        self.azimuth = (
            round(azimuth_data.actualPosition, ndigits=2)
            if not isinstance(azimuth_data, Exception)
            else self.azimuth_default
        )
        self.camrot = (
            round(rotator_data.actualPosition, ndigits=2)
            if not isinstance(rotator_data, Exception)
            else self.camrot_default
        )

        if any(
            [
                isinstance(elevation_data, Exception),
                isinstance(azimuth_data, Exception),
                isinstance(rotator_data, Exception),
            ]
        ):
            self.log.warning(
                "Cannot determine one or more of the axis position. Using default value."
            )

        await self.model.set_telescope_position(
            telalt=self.elevation,
            telaz=self.azimuth,
            camrot=self.camrot,
        )

    async def run_telemetry_loop(self) -> None:
        """Run telemetry loop.

        The telemetry loop will run while the CSC is in disable or enabled
        state.
        """

        assert self.model is not None

        while self._run_telemetry_loop:
            status = await self.model.get_status()
            t2sa_status = T2SAStatus(getattr(T2SAStatus, status))
            if t2sa_status == T2SAStatus.READY:
                self.laser_status_ready.set()
            else:
                self.laser_status_ready.clear()

            await self.evt_t2saStatus.set_write(status=t2sa_status)

            status = await self.model.laser_status()

            if status == "LOW":
                laser_status = LaserStatus.OFF
            elif status == "LON":
                laser_status = LaserStatus.ON
            else:
                self.log.warning(f"Invalid Laser Status: {status}")
                laser_status = LaserStatus.NOT_CONNECTED

            await self.evt_laserStatus.set_write(status=laser_status)

            await asyncio.sleep(self.heartbeat_interval)

    async def stop_telemetry_loop(self) -> None:
        """Stop the telemetry loop and clean up.

        If the telemetry loop task is still running when this method is called,
        it waits 2 heartbeat interval for it to finish and then proceed to
        cancel it. If any unexpected exception occurs, log them and continue.

        The idea is to allow the telemetry loop some time to finish before
        canceling it, which sometimes help prevent issues with sockets hanging
        out.
        """

        if not self.telemetry_loop_task.done():
            self._run_telemetry_loop = False
            wait_finish_interval = self.heartbeat_interval * 2
            self.log.debug(
                f"Telemetry loop task still running. Waiting {wait_finish_interval}s for it to finish."
            )
            try:
                await asyncio.wait_for(
                    self.telemetry_loop_task, timeout=wait_finish_interval
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

    def in_tolerance(self, coords: dict[str, str | float]) -> bool:
        """Returns true if the specified coords are in tolerance.

        Parameters
        ----------
        coords : `Dict`
            Dict containing coordinates
        """
        raise NotImplementedError()


def run_lasertracker() -> None:
    """Run the LaserTracker CSC."""
    asyncio.run(LaserTrackerCsc.amain(index=SalIndex))
