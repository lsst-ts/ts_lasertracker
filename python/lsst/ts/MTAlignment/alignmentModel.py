
import asyncio
from enum import IntEnum


class LaserStatus(IntEnum):
    LASERNOTCONNECTED = -1
    LASEROFF = 0
    LASERON = 1


class TrackerStatus(IntEnum):
    READY = 1
    TWOFACE = 2
    ADM = 3
    DRIFT = 4
    EMP = 5
    ERR = 6


class AlignmentModel():

    def __init__(self):
        self.server_address = ("172.17.0.3", 50000)
        self.connected = False
        self.reader = None
        self.writer = None
        self.first_measurement = True

        self.trackerstatus = None
        self.laserstatus = None
        self.com_lock = asyncio.Lock()

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(*self.server_address)
        self.connected = True
        asyncio.create_task(self.status_loop())

    async def status_loop(self):
        """
        pings T2SA for status every second, and updates internal state.
        """
        while self.connected:
            stat = await self.status()
            if stat == "READY":
                self.trackerstatus = TrackerStatus.READY
            elif stat == "2FACE":
                self.trackerstatus = TrackerStatus.TWOFACE
            elif stat == "ADM":
                self.trackerstatus = TrackerStatus.ADM
            elif stat == "DRIFT":
                self.trackerstatus = TrackerStatus.DRIFT
            elif stat == "EMP":
                self.trackerstatus = TrackerStatus.EMP
            elif stat == "ERR":
                self.trackerstatus = TrackerStatus.ERR
            await asyncio.sleep(1)

    async def wait_for_ready(self):
        with self.com_lock:
            wait_states = ("EMP\r\n")
            msg = bytes("?STAT\r\n", 'ascii')
            self.writer.write(msg)
            await self. writer.drain()
            data = await  self.reader.read(64)
            stat = data.decode()
            if stat == "INIT" or stat == "INIT\r\n":
                print("waiting for init")
                await asyncio.sleep(5)
            while stat in wait_states:
                print("...")
                await asyncio.sleep(0.3)
                self.writer.write(msg)
                await self. writer.drain()
                data = await  self.reader.read(64)
                stat = data.decode()
            await asyncio.sleep(0.5)

    async def send_msg(self, msg):
        msg = msg + "\r\n"
        if type(msg) == str:  # this may move
            msg = bytes(msg, 'ascii')
        print(f"sending {msg}")
        with self.com_lock:
            self.writer.write(msg)
            await self. writer.drain()
            data = await self.reader.readuntil(separator=bytes("\n", 'ascii'))
            print(f'Received: {data.decode()!r}')
            return data.decode()

    async def status(self):
        response = await self.send_msg("?STAT")
        return response

    async def laser_status(self):
        """
        Query tracker laser status, and update model state accordingly
        """

        msg = self.msgformat("?LSTA")
        data = await self.send_msg(msg)
        if data == "LNC":
            self.laserstatus = LaserStatus.LASERNOTCONNECTED
        elif data == "LOFF":
            self.laserstatus = LaserStatus.LASEROFF
        elif data == "LON":
            self.laserstatus = LaserStatus.LASERON

    async def laser_on(self):
        """
        Turns the Tracker Laser on (for warmup purposes)
        """

        msg = "!CMDTLON"
        data = await self.send_msg(msg)
        return data

    async def laser_off(self):
        """
        Turns the Tracker Laser off
        """

        msg = "!CMDTLOFF"
        data = await self.send_msg(msg)
        return data

    async def measure_m2(self):
        """
        Execute M2 measurement plan
        """

        if self.first_measurement:
            print("first measurement, waiting for tracker warmup")
            await asyncio.sleep(5)
            self.first_measurement = False
        print("measure m2")
        msg = "!CMDEXE:M2"
        print(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        data = await self.send_msg(msg)
        return data

    async def measure_m1m3(self):
        """
        Execute M1M3 measurement plan
        """

        if self.first_measurement:
            print("first measurement, waiting for tracker warmup")
            await asyncio.sleep(5)
            self.first_measurement = False
        print("measure m1m3")
        msg = "!CMDEXE:M1M3"
        print(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        data = await self.send_msg(msg)
        return data

    async def measure_cam(self):
        """
        Execute Camera measurement plan
        """

        if self.first_measurement:
            print("first measurement, waiting for tracker warmup")
            await asyncio.sleep(2)
            self.first_measurement = False
        print("measure cam")
        msg = "!CMDEXE:CAM"
        print(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        data = await self.send_msg(msg)
        return data

    async def query_m2_position(self):
        """
        Query M2 position after running the M2 MP
        """

        print("query m2")
        msg = "?POS M2"
        data = await self.send_msg(msg)
        return data

    async def query_m1m3_position(self):
        """
        Query M1m3 position after running the MP
        """

        print("query m1m3")
        msg = "?POS M1M3"
        data = await self.send_msg(msg)
        return data

    async def query_cam_position(self):
        """
        Query cam position after running the MP
        """

        print("query cam")
        msg = "?POS CAM"
        data = await self.send_msg(msg)
        return data

    async def query_m2_offset(self):
        """
        Query M2 offset from nominal
        """

        msg = "?OFFSET M2"
        data = await self.send_msg(msg)
        return data

    async def query_m1m3_offset(self):
        """
        Query M1m3 offset from nominal
        """

        msg = "?OFFSET M1M3"
        data = await self.send_msg(msg)
        return data

    async def query_cam_offset(self):
        """
        Query cam offset from nominal + current rotation
        """

        msg = "?OFFSET CAM"
        data = await self.send_msg(msg)
        return data

    async def clear_errors(self):
        """
        Clear errors, or return a -300 if we cant clear them
        """

        msg = "!CLERCL"
        data = await self.send_msg(msg)
        return data

    async def set_randomize_points(self, val):
        """
        Measure the points in the SpatialAnalyzer database in a random order

        val: Boolean
        """

        if val:
            msg = "SET_RANDOMIZE_POINTS:1"
        else:
            msg = "SET_RANDOMIZE_POINTS:0"
        data = await self.send_msg(msg)
        return data

    async def twoFace_check(self, pointgroup):
        """
        Runs the 2 face check against a given point group

        pointgroup: String
        """

        msg = "!2FACE_CHECK:" + pointgroup
        data = await self.send_msg(msg)
        return data

    async def measure_drift(self, pointgroup):
        """
        Measure drift relative to a nominal point group

        pointgroup: string
        """

        msg = "!MEAS_DRIFT:" + pointgroup
        data = await self.send_msg(msg)
        return data

    async def measure_single_point(self, pointgroup, target):
        """
        Point at target, lock on and start measuring target using measurement profile

        pointgroup: String
        target: String
        """

        msg = f"!MEAS_SINGLE_POINT:{pointgroup};{target}"
        data = await self.send_msg(msg)
        return data

    async def single_point_measurement_profile(self, profile):
        """
        Not 100% clear what this one does. Just set the profile?

        profile: String
        """

        msg = "!SINGLE_POINT_MEAS_PROFILE:" + profile
        data = await self.send_msg(msg)
        return data

    async def generate_report(self, reportname):
        """
        Generate report

        reportname: String
        """

        msg = "!GEN_REPORT:" + reportname
        data = await self.send_msg(msg)
        return data

    async def set_2face_tolerance(self, tolerance):
        """
        default tolerance is 0.001 dec deg

        tolerance: float (TODO find out what the range is)
        """

        msg = "!SET_2FACE_TOL:" + tolerance
        data = await self.send_msg(msg)
        return data

    async def set_drift_tolerance(self, rms_tol, max_tol):
        """
        rms_tol default 0.050 mm
        max_tol default 0.1 mm
        """

        msg = f"!SET_DRIFT_TOL:{rms_tol};{max_tol}"
        data = await self.send_msg(msg)
        return data

    async def set_ls_tolerance(self, rms_tol, max_tol):
        """
        rms_tol default 0.050 mm
        max_tol default 0.1 mm
        not actually sure how this one differs from the previous...
        """

        msg = f"!SET_LS_TOL:{rms_tol};{max_tol}"
        data = await self.send_msg(msg)
        return data

    async def load_template_file(self, filepath):
        """
        Load template file

        filepath: String
        """

        msg = "!LOAD_SA_TEMPLATE_FILE:" + filepath
        data = await self.send_msg(msg)
        return data

    async def set_reference_group(self, pointgroup):
        """
        Nominal pt grp to locate station to and provide data relative to.

        pointgroup: String

        """

        msg = "!SET_REFERENCE_GROUP:" + pointgroup
        data = await self.send_msg(msg)
        return data

    async def set_working_frame(self, workingframe):
        """
        Make workingframe the working frame:

        workingframe: string
        """

        msg = "!SET_WORKING_FRAME:" + workingframe
        data = await self.send_msg(msg)
        return data

    async def new_station(self):
        """
        A new station is added and made to be the active instrument.
        """

        msg = "!NEW_STATION"
        data = await self.send_msg(msg)
        return data

    async def save_sa_jobfile(self, filepath):
        """
        Save a jobfile

        filepath: String
        """

        msg = "!SAVE_SA_JOBFILE:" + filepath
        data = await self.send_msg(msg)
        return data

    async def set_station_lock(self, val):
        """
        Prevents SA from automatically jumping stations when it detects that the tracker has drifted.

        val: Boolean
        """
        if val:
            msg = "!SET_STATION_LOCK:1"
        else:
            msg = "!SET_STATION_LOCK:0"
        data = await self.send_msg(msg)
        return data

    async def reset_t2sa(self):
        """
        Reboots the T2SA and SA components
        """

        msg = "!RESET_T2SA"
        data = await self.send_msg(msg)
        return data

    async def halt(self):
        """
        Commands T2SA to halt any measurement plans currently executing,
        and return to ready state
        """

        msg = "!HALT"
        data = await self.send_msg(msg)
        return data

    async def publish_telescope_position(self, telalt, telaz, camrot):
        """
        Command in which TCS informs T2SA of the telescope’s current
        position and camera rotation angle, to be used ahead of a
        measurement cmd.
        TODO: we need to add dome position to this for calscreen alignment

        telalt: float
        telaz: float
        camrot: float
        """

        msg = f"PUBLISH_ALT_AZ_ROT:{telalt};{telaz};{camrot}"
        data = await self.send_msg(msg)
        return data

    async def set_num_samples(self, numsamples):
        """
        This is the number of times the tracker samples each point
        in order to get one (averaged) measurement

        numsamples: int
        """

        msg = f"SET_NUM_SAMPLES:{numsamples}"
        data = await self.send_msg(msg)
        return data

    async def set_num_iterations(self, numiters):
        """
        This is the number of times we repeat an auto-measurement
        of a point group

        numiters: int
        """

        msg = f"SET_NUM_ITERATIONS:{numiters}"
        data = await self.send_msg(msg)
        return data

    async def increment_measured_index(self, idx):
        """
        Increment to measured point group index by idx

        idx: int
        """

        msg = f"INC_MEAS_INDEX:{idx}"
        data = await self.send_msg(msg)
        return data

    async def disconnect(self):
        self.writer.close()
        self.connected = False

    def msgformat(self, st):
        '''
        takes a string, converts to bytes, and adds the end-of-line characters
        '''
        msg = bytes(st + "\r\n", 'ascii')
        return msg
