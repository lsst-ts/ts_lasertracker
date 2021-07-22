from .alignmentModel import AlignmentModel
from lsst.ts import salobj
import enum
from .config_schema import CONFIG_SCHEMA
from . import __version__
import logging


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
        self, config_dir=None, initial_state=salobj.State.STANDBY, simulation_mode=0, use_port_zero=False
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

        self.log.addHandler(logging.StreamHandler())
        self.log.setLevel(logging.DEBUG)

        # temporary variables for position; these will eventually be supplied
        # by the TMA and camera rotator CSCs.
        self.elevation = 90
        self.azimuth = 0
        self.camrot = 0
        self.use_port_zero = use_port_zero

    async def handle_summary_state(self):
        if self.disabled_or_enabled:
            if self.model is None:
                self.model = AlignmentModel(
                    self.config.t2sa_ip,
                    self.config.t2sa_port,
                    log=self.log
                )
                self.model.simulation_mode = self.simulation_mode
                await self.model.connect(self.config.t2sa_ip, self.config.t2sa_port)
                self.log.debug(f"connected to t2sa at {self.model.host}:{self.model.port}")
        else:
            if self.model is not None:
                await self.model.disconnect()
                self.model = None

    async def configure(self, config):
        self.config = config
        if self.model is not None:
            if self.model.connected:
                await self.model.disconnect()
            await self.model.connect(self.config.t2sa_ip, self.config.t2sa_port)

    @staticmethod
    async def get_config_pkg(self):
        return "ts_config_mttcs"

    async def do_measureTarget(self, data):
        self.log.debug("measure Target")
        """Measure and return coordinates of a target. Options are
        M1M3, M2, CAM, and DOME"""
        self.assert_enabled()
        if data.target == "CAM":
            ack = await self.model.measure_cam()
            result = await self.model.query_cam_position()
        elif data.target == "M2":
            ack = await self.model.measure_m2()
            result = await self.model.query_m2_position()
        elif data.target == "M1M3":
            self.log.debug("measure m1m3")
            ack = await self.model.measure_m1m3()
            result = await self.model.query_m1m3_position()
        self.log.debug(result) # eventually we will publish an event with the measured coordinates

    async def do_align(self, data):
        """Perform correction loop"""
        self.assert_enabled()

    async def do_healthCheck(self, data):
        """run healthcheck script"""
        self.assert_enabled()

    async def do_laserPower(self, data):
        """put the laser in sleep state"""
        self.assert_enabled()

    async def do_powerOff(self, data):
        """full power off of tracker and interface"""
        self.assert_enabled()

    async def do_measurePoint(self, data):
        """measure and return coords of a specific point"""
        self.assert_enabled()

    async def do_pointDelta(self, data):
        """return a vector between two points"""
        self.assert_enabled()

    async def do_setReferenceGroup(self, data):
        """Nominal point group to locate tracker station to and provide data
        relative to"""
        self.assert_enabled()

    async def do_setWorkingFrame(self, data):
        """attempt to set the passed string as the SpatialAnalyzer working
        frame"""
        self.assert_enabled()

    async def do_halt(self, data):
        """halts any executing measurement plan and returns to ready state"""
        self.assert_enabled()

    async def do_loadSATemplateFile(self, data):
        """SA Template file path and name. This is in the filesystem on the
        T2SA host."""
        self.assert_enabled()

    async def do_measureDrift(self, data):
        """measure tracker drift"""
        self.assert_enabled()

    async def do_resetT2SA(self, data):
        """reboots t2sa and SA"""
        self.assert_enabled()

    async def do_newStation(self, data):
        """create new tracker station"""
        self.assert_enabled()

    async def do_saveJobfile(self, data):
        """save job file"""
        self.assert_enabled()

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
