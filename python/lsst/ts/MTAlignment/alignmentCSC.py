from .alignmentModel import AlignmentModel
from lsst.ts import salobj
import enum
from .config_schema import CONFIG_SCHEMA
from . import __version__


class AlignmentDetailedState(enum.IntEnum):
    DISABLED = 1
    ENABLED = 2
    FAULT = 3
    OFFLINE = 4
    STANDBY = 5
    MEASURING = 6
    TWOFACE_CHECK = 7
    ADM_CHECK = 8
    DRIFT_CHECK = 9


class AlignmentCSC(salobj.ConfigurableCsc):
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
        self, config_dir=None, initial_state=salobj.State.STANDBY, simulation_mode=0
    ):
        super().__init__(
            "MTAlignment",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
        )
        self.model = None
        self.max_iters = 3

        # temporary variables for position; these will eventually be supplied
        # by the TMA and camera rotator CSCs.
        self.elevation = 90
        self.azimuth = 0
        self.camrot = 0

    async def handle_summary_state(self):
        if self.disabled_or_enabled:
            if self.model is None:
                self.model = AlignmentModel(self.config.t2sa_ip, self.config.t2sa_port)
        else:
            self.model = None

    async def configure(self, config):
        self.config = config

    @staticmethod
    async def get_config_pkg(self):
        return "ts_config_mttcs"

    async def do_measureTarget(self):
        """Measure and return coordinates of a target. Options are
        M1M3, M2, CAM, and DOME"""
        pass

    async def do_align(self):
        """Perform correction loop"""
        pass

    async def do_healthCheck(self):
        """run healthcheck script"""
        pass

    async def do_laserPower(self):
        """put the laser in sleep state"""
        pass

    async def do_powerOff(self):
        """full power off of tracker and interface"""
        pass

    async def do_measurePoint(self):
        """measure and return coords of a specific point"""
        pass

    async def do_pointDelta(self):
        """return a vector between two points"""
        pass

    async def do_setReferenceGroup(self):
        """Nominal point group to locate tracker station to and provide data
        relative to"""
        pass

    async def do_setWorkingFrame(self):
        """attempt to set the passed string as the SpatialAnalyzer working
        frame"""
        pass

    async def do_halt(self):
        """halts any executing measurement plan and returns to ready state"""
        pass

    async def do_loadSATemplateFile(self):
        """SA Template file path and name. This is in the filesystem on the
        T2SA host."""
        pass

    async def do_measureDrift(self):
        """measure tracker drift"""
        pass

    async def do_resetT2SA(self):
        """reboots t2sa and SA"""
        pass

    async def do_newStation(self):
        """create new tracker station"""
        pass

    async def do_saveJobfile(self):
        """save job file"""
        pass

    async def correction_loop(self):
        await self.model.set_telescope_position(
            self.elevation, self.azimuth, self.camrot
        )

        await self.model.measure_m1m3()
        aligned = False
        loopcount = 1
        while not aligned:
            print("Loop Number: " + str(loopcount))
            await self.model.measure_cam()
            await self.model.measure_m2()

            camOffset = self.parse_offsets(await self.model.query_cam_offset("CAM"))
            m2Offset = self.parse_offsets(await self.model.query_m2_offset("M2"))

            if self.in_tolerance(camOffset) and self.in_tolerance(m2Offset):
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
            coordsDict[bits[0][0]] = bits[0][1]

            # coords
            for s in bits[1:7]:
                coordsDict[s[0]] = float(s[1])

            # timestamp
            coordsDict["Timestamp"] = f"{bits[7][0]}:{bits[7][1]}:{bits[7][2]}"
        except ValueError or IndexError:
            raise Exception(f"Failed to parse coordinates string '{t2sa_string}' received from T2SA.")
        return coordsDict

    def in_tolerance(self, coords):
        """
        Takes coordinates returns true/false based on whether they are within
        tolerance.

        Parameters
        ----------

        coords : `Dict`
            Dict containing coordinates
        """

        print(coords)
        return False
