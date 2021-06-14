from .alignmentModel import AlignmentModel
from lsst.ts import salobj
import enum
from .config_schema import CONFIG_SCHEMA
from . import __version__


class ASCDetailedState(enum.IntEnum):
    DISABLED = 1
    ENABLED = 2
    FAULT = 3
    OFFLINE = 4
    STANDBY = 5
    MEASURING = 6


class AlignmentCSC(salobj.ConfigurableCsc):
    version = __version__
    valid_simulation_modes = (0, 1)

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

    async def get_config_pkg(self):
        pass

    async def do_align(self):
        pass

    async def do_healthCheck(self):
        pass

    async def do_laserPower(self):
        pass

    async def do_measurePoint(self):
        pass

    async def do_measureTarget(self):
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
            the ascii string from T2SA
        """
        bits = [b.split(":") for b in t2sa_string.split(";")]
        coordsDict = {}

        # ref frame
        coordsDict[bits[0][0]] = bits[0][1]

        # coords
        for s in bits[1:7]:
            coordsDict[s[0]] = float(s[1])

        # timestamp
        coordsDict["Timestamp"] = f"{bits[7][0]}:{bits[7][1]}:{bits[7][2]}"
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
