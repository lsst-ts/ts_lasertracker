
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
        msg = self.msgformat("?LSTA")
        data = await self.send_msg(msg)
        if data == "LNC":
            self.laserstatus = LaserStatus.LASERNOTCONNECTED
        elif data == "LOFF":
            self.laserstatus = LaserStatus.LASEROFF
        elif data == "LON":
            self.laserstatus = LaserStatus.LASERON

    async def laser_on(self):
        msg = "!CMDTLON"
        data = await self.send_msg(msg)
        return data

    async def laser_off(self):
        msg = "!CMDTLOFF"
        data = await self.send_msg(msg)
        return data

    async def measure_m2(self):
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
        print("query m2")
        msg = "?POS M2"
        data = await self.send_msg(msg)
        return data

    async def query_m1m3_position(self):
        print("query m1m3")
        msg = "?POS M1M3"
        data = await self.send_msg(msg)
        return data

    async def query_cam_position(self):
        print("query cam")
        msg = "?POS CAM"
        data = await self.send_msg(msg)
        return data

    async def query_m2_offset(self):
        msg = "?OFFSET M2"
        data = await self.send_msg(msg)
        return data

    async def query_m1m3_offset(self):
        msg = "?OFFSET M1M3"
        data = await self.send_msg(msg)
        return data

    async def query_cam_offset(self):
        msg = "?OFFSET CAM"
        data = await self.send_msg(msg)
        return data

    async def clear_errors(self):
        msg = "!CLERCL"
        data = await self.send_msg(msg)
        return data
    
    async def set_randomize_points(self, val):
        """
        val is bool
        """
        if val:
            msg = "SET_RANDOMIZE_POINTS:1"
        else:
            msg = "SET_RANDOMIZE_POINTS:0"
        data = await self.send_msg(msg)
        return data

    async def twoFace_check(self, pointgroup):
        msg = "!2FACE_CHECK:" + pointgroup
        data = await self.send_msg(msg)
        return data

    async def measure_drift(self, pointgroup):
        msg = "!MEAS_DRIFT:" + pointgroup
        data = await self.send_msg(msg)
        return data

    async def measure_single_point(self, pointgroup, target):
        msg = f"!MEAS_SINGLE_POINT:{pointgroup};{target}"
        data = await self.send_msg(msg)
        return data

    async def single_point_measurement_profile(self, profile):
        msg = "!SINGLE_POINT_MEAS_PROFILE:" + profile
        data = await self.send_msg(msg)
        return data

    async def generate_report(self, reportname):
        msg = "!GEN_REPORT:" + reportname
        data = await self.send_msg(msg)
        return data

    async def set_2face_tolerance(self, tolerance)
        """
        default tolerance is 0.001 dec deg
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
        msg = "!LOAD_SA_TEMPLATE_FILE:" + filepath
        data = await self.send_msg(msg)
        return data

    async def set_reference_group(self, pointgroup):
        msg = "!SET_REFERENCE_GROUP:" + pointgroup
        data = await self.send_msg(msg)
        return data
    
    async def set_working_frame(self, workingframe):
        msg = "!SET_WORKING_FRAME:" + workingframe
        data = await self.send_msg(msg)
        return data

    async def new_station(self)
        msg = "!NEW_STATION"
        data = await self.send_msg(msg)
        return data

    async def save_sa_jobfile(self, filepath):
        msg = "!SAVE_SA_JOBFILE:" + filepath
        data = await self.send_msg(msg)
        return data

    async def set_station_lock(self, val):
        """
        val is bool
        """
        if val:
            msg = "!SET_STATION_LOCK:1"
        else:
            msg = "!SET_STATION_LOCK:0"
        data = await self.send_msg(msg)
        return data

    async def reset_t2sa(self)
        msg = "!RESET_T2SA"
        data = await self.send_msg(msg)
        return data

    async def halt(self)
        msg = "!HALT
        data = await self.send_msg(msg)
        return data

    async def publish_telescope_position(self, telalt, telaz, camrot)
        msg = f"PUBLISH_ALT_AZ_ROT:{telalt};{telaz};{camrot}"
        data = await self.send_msg(msg)
        return data

    async def set_num_samples(self, numsamples):
        msg = f"SET_NUM_SAMPLES:{numsamples}"
        data = await self.send_msg(msg)
        return data

    async def set_num_iterations(self, numiters):
        msg = f"SET_NUM_ITERATIONS:{numiters}"
        data = await self.send_msg(msg)
        return data

    async def increment_measured_index(self, idx):
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
