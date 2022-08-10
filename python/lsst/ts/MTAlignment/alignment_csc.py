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

__all__ = ["AlignmentDetailedState", "AlignmentCSC", "run_mtalignment"]

import asyncio
import enum

from lsst.ts import salobj

from . import __version__
from .alignment_model import AlignmentModel
from .config_schema import CONFIG_SCHEMA


# The following targets must appear in config.targets
REQUIRED_TARGETS = {"CAM", "M1M3", "M2"}


class AlignmentDetailedState(enum.IntEnum):
    DISABLED = 1
    ENABLED = 2
    FAULT = 3
    OFFLINE = 4
    STANDBY = 5
    MEASURING = 6
    TWOFACE_CHECK = 7
    DRIFT_CHECK = 8


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

    version = __version__
    valid_simulation_modes = (0, 1, 2)
    simulation_help = """
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
        config_dir=None,
        initial_state=salobj.State.STANDBY,
        override="",
        simulation_mode=0,
    ):
        super().__init__(
            name="MTAlignment",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )
        self.model = None
        self.max_iters = 3

        # temporary variables for position; these will eventually be supplied
        # by the TMA and camera rotator CSCs.
        self.elevation = 90
        self.azimuth = 0
        self.camrot = 0
        self.last_measurement = None

    async def handle_summary_state(self):
        if self.disabled_or_enabled:
            if self.model is None:
                self.model = AlignmentModel(
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
        else:
            if self.model is not None:
                await self.model.disconnect()
                self.model = None

    async def configure(self, config):
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
    def get_config_pkg():
        return "ts_config_mttcs"

    async def do_measureTarget(self, data):
        self.log.debug("measure Target")
        """Measure and return coordinates of a target. Options are
        M1M3, M2, CAM, and DOME"""
        self.assert_enabled()
        if data.target not in self.config.targets:
            raise salobj.ExpectedError(
                f"Unknown target {data.target}; must one of {self.config.targets}"
            )
        await self.model.measure_target(data.target)
        result = await self.model.get_target_position(data.target)
        self.log.debug(
            self.parse_offsets(result)
        )  # TODO publish an event with the measured coords
        self.last_measurement = self.parse_offsets(result)
        await self.evt_positionPublish.set_write(target=self.last_measurement["RefFrame"],
          dX=self.last_measurement["X"],
          dY=self.last_measurement["Y"],
          dZ=self.last_measurement["Z"],
          dRX=self.last_measurement["Rx"],
          dRY=self.last_measurement["Ry"],
          dRZ=self.last_measurement["Rz"])

    async def do_align(self, data):
        """Perform correction loop"""
        self.assert_enabled()
        await self.model.align()

    async def do_healthCheck(self, data):
        """run healthcheck script"""
        self.assert_enabled()
        await self.model.twoface_check()
        await self.model.measure_drift()

    async def do_laserPower(self, data):
        """put the laser in sleep state"""
        self.assert_enabled()
        if data.power == 0:
            await self.model.laser_off()
        else:
            await self.model.laser_on()

    async def do_powerOff(self, data):
        """full power off of tracker and interface"""
        self.assert_enabled()
        await self.model.tracker_off()

    async def do_measurePoint(self, data):
        """measure and return coords of a specific point"""
        self.assert_enabled()
        await self.model.measure_single_point(
            data.collection, data.pointgroup, data.target
        )

    async def do_pointDelta(self, data):
        """publish an event containing a vector between two points"""
        self.assert_enabled()
        data = await self.model.get_point_delta(
            data.collection_A,
            data.pointgroup_A,
            data.target_A,
            data.collection_B,
            data.pointgroup_B,
            data.target_B,
        )

    async def do_setReferenceGroup(self, data):
        """Nominal point group to locate tracker station to and provide data
        relative to"""
        self.assert_enabled()
        await self.model.set_reference_group(data.pointgroup)

    async def do_setWorkingFrame(self, data):
        """attempt to set the passed string as the SpatialAnalyzer working
        frame"""
        self.assert_enabled()
        await self.model.set_working_frame(data.workingFrame)

    async def do_halt(self, data):
        """halts any executing measurement plan and returns to ready state"""
        self.assert_enabled()
        await self.model.halt()

    async def do_loadSATemplateFile(self, data):
        """SA Template file path and name. This is in the filesystem on the
        T2SA host."""
        self.assert_enabled()
        await self.model.load_template_file(data.file)

    async def do_measureDrift(self, data):
        """measure tracker drift"""
        self.assert_enabled()
        await self.model.measure_drift(data.pointgroup)

    async def do_resetT2SA(self, data):
        """reboots t2sa and SA"""
        self.assert_enabled()
        await self.model.reset_t2sa()

    async def do_newStation(self, data):
        """create new tracker station"""
        self.assert_enabled()
        await self.model.new_station(data.newStation)

    async def do_saveJobfile(self, data):
        """save job file"""
        self.assert_enabled()
        await self.model.save_sa_jobfile(data.file)

    async def correction_loop(self):
        await self.model.set_telescope_position(
            self.elevation, self.azimuth, self.camrot
        )

        await self.model.measure_target("M1M3")
        aligned = False
        loopcount = 1
        while not aligned:
            self.log.info(f"Loop iteration: {loopcount}")
            await self.model.measure_target("CAM")
            await self.model.measure_target("M2")

            cam_offset = self.parse_offsets(await self.model.get_target_offset("CAM"))
            m2_offset = self.parse_offsets(await self.model.get_target_offset("M2"))

            if self.in_tolerance(cam_offset) and self.in_tolerance(m2_offset):
                break
            elif loopcount >= self.max_iters:
                break
            else:
                loopcount += 1

    def parse_offsets(self, t2sa_string):
        """
        Takes a string containing spatial coordinates  from T2SA, and returns
        a dict with the following keys: RefFrame, X, Y, Z, Rx, Ry, Rz, and
        Timestamp

        Parameters
        ----------

        t2sa_string : `str`
            the ascii string from T2SA. We expect an ascii string delimited
            with colons and semicolons, formatted like this:

            <s>;X:<n>;Y:<n>;Z:<n>;Rx:<n>;Ry:<n>;Rz:<n>;<date>

            where <s> is the name of the reference frame and <n> is a
            floating point value.
        """
        bits = [b.split(":") for b in t2sa_string.split(";")]
        coordsDict = {}
        try:
            # ref frame
            coordsDict["RefFrame"] = bits[0][1]

            # coords
            for s in bits[1:7]:
                coordsDict[s[0]] = float(s[1])

            # timestamp
            coordsDict["Timestamp"] = f"{bits[7][0]}:{bits[7][1]}:{bits[7][2]}"
        except ValueError or IndexError:
            raise Exception(
                f"Failed to parse coordinates string '{t2sa_string}' received from T2SA."
            )
        return coordsDict

    def in_tolerance(self, coords):
        """Returns true if the specified coords are in tolerance.

        Parameters
        ----------

        coords : `Dict`
            Dict containing coordinates
        """
        raise NotImplementedError()


def run_mtalignment():
    """Run the MTAlignment CSC."""
    asyncio.run(AlignmentCSC.amain(index=None))
