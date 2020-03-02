import asyncio
from enum import IntEnum
import logging


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

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.log = logging.getLogger()
        self.connected = False
        self.reader = None
        self.writer = None
        self.first_measurement = True

        self.com_lock = asyncio.Lock()

    async def connect(self):
        """
        Connect to the T2SA host
        """
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        self.connected = True

    async def disconnect(self):
        self.writer.close()
        self.connected = False

    async def wait_for_ready(self):
        """
        Checks to see if the tracker is executing a measurement plan.
        If so, hold on to control until we start getting a ready signal
        from the tracker. This is likely to be deprecated later.
        """
        async with self.com_lock:
            wait_states = ("EMP\r\n")
            msg = bytes("?STAT\r\n", 'ascii')
            self.writer.write(msg)
            await self. writer.drain()
            data = await self.reader.read(64)
            stat = data.decode()
            if stat == "INIT" or stat == "INIT\r\n":
                self.log.debug("waiting for init")
                await asyncio.sleep(5)
            while stat in wait_states:
                await asyncio.sleep(0.3)
                self.writer.write(msg)
                await self. writer.drain()
                data = await self.reader.read(64)
                stat = data.decode()
            await asyncio.sleep(0.5)

    async def send_msg(self, msg):
        """
        Formats and sends a message to T2SA.

        Parameters
        ----------
        msg : `str`
            String message to send to T2SA controller.
        """
        msg = msg + "\r\n"
        if type(msg) == str:  # this may move
            msg = bytes(msg, 'ascii')
        self.log.debug(f"sending {msg}")
        async with self.com_lock:
            self.writer.write(msg)
            await self. writer.drain()
            data = await self.reader.readuntil(separator=bytes("\n", 'ascii'))
            self.log.debug(f'Received: {data.decode()!r}')
            return data.decode()

    async def check_status(self):
        """
        query T2SA for status
        """
        response = await self.send_msg("?STAT")
        return response

    async def send_string(self, message):
        """
        sends a string

        Parameters
        ----------
        message : `str`
            characters to send to T2SA.
        """
        response = await self.send_msg(message)
        return response

    async def laser_status(self):
        """
        Query laser tracker's laser status, and update model state accordingly
        """

        data = await self.send_msg("?LSTA")
        return data

    async def laser_on(self):
        """
        Turns the Tracker Laser on (for warmup purposes)
        """
        data = await self.send_msg("!LST:1")
        return data

    async def laser_off(self):
        """
        Turns the Tracker Laser off
        """
        data = await self.send_msg("!LST:0")
        return data

    async def measure_m2(self):
        """
        Execute M2 measurement plan
        """
        self.log.debug("measure m2")
        msg = "!CMDEXE:M2"
        self.log.debug(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        data = await self.send_msg(msg)
        return data

    async def measure_m1m3(self):
        """
        Execute M1M3 measurement plan
        """
        self.log.debug("measure m1m3")
        msg = "!CMDEXE:M1M3"
        self.log.debug(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        data = await self.send_msg(msg)
        return data

    async def measure_cam(self):
        """
        Execute Camera measurement plan
        """

        if self.first_measurement:
            self.log.debug("first measurement, waiting for tracker warmup")
            await asyncio.sleep(2)
            self.first_measurement = False
        self.log.debug("measure cam")
        msg = "!CMDEXE:CAM"
        self.log.debug(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        data = await self.send_msg(msg)
        return data

    async def query_m2_position(self):
        """
        Query M2 position after running the M2 MP
        Position queries are always in terms of M1M3 coordinate frame
        """

        self.log.debug("query m2")
        msg = "?POS M2"
        data = await self.send_msg(msg)
        return data

    async def query_m1m3_position(self):
        """
        Query M1m3 position after running the MP
        Position queries are always in terms of M1M3 coordinate frame
        """

        self.log.debug("query m1m3")
        msg = "?POS M1M3"
        data = await self.send_msg(msg)
        return data

    async def query_cam_position(self):
        """
        Query cam position after running the MP
        Position queries are always in terms of M1M3 coordinate frame
        """

        self.log.debug("query cam")
        msg = "?POS CAM"
        data = await self.send_msg(msg)
        return data

    async def query_m2_offset(self, refPtGrp="M1M3"):
        """
        Query M2 offset from nominal

        Parameters
        ----------
        refPtGrp : String
            name of pointgroup that will be used as the frame of reference for the offset.
        """

        msg = "?OFFSET:" + refPtGrp +  ";M2"
        data = await self.send_msg(msg)
        return data

    async def query_m1m3_offset(self, refPtGrp="M1M3"):
        """
        Query M1m3 offset from nominal
        
        Parameters
        ----------
        refPtGrp : String
            name of pointgroup that will be used as the frame of reference for the offset.
        """

        msg = "?OFFSET:" + refPtGrp + ";M1M3"
        data = await self.send_msg(msg)
        return data

    async def query_cam_offset(self, refPtGrp="M1M3"):
        """
        Query cam offset from nominal + current rotation

        Parameters
        ----------
        refPtGrp : String
            name of pointgroup that will be used as the frame of reference for the offset.
        """

        msg = "?OFFSET:" + refPtGrp + ";CAM"
        data = await self.send_msg(msg)
        return data

    async def clear_errors(self):
        """
        Clear errors, or return a -300 if we cant clear them
        """

        msg = "!CLERCL"
        data = await self.send_msg(msg)
        return data

    async def set_randomize_points(self, randomize_points):
        """
        Measure the points in the SpatialAnalyzer database in a random order

        Parameters
        ----------
        randomize_points : Boolean
            True to randomize point order
        """

        if randomize_points:
            msg = "SET_RANDOMIZE_POINTS:1"
        else:
            msg = "SET_RANDOMIZE_POINTS:0"
        data = await self.send_msg(msg)
        return data

    async def set_power_lock(self, power_lock):
        """
        enable/disable the Tracker's IR camera which helps it find SMRs, but 
        can also cause it to lock on to thee wrong one sometimes.

        Parameters
        ----------
        power_lock : Boolean
            True to enable the IR camera assist
        """

        if power_lock:
            msg = "SET_POWER_LOCK:1"
        else:
            msg = "SET_POWER_LOCK:0"
        data = await self.send_msg(msg)
        return data

    async def twoFace_check(self, pointgroup):
        """
        Runs the 2 face check against a given point group

        Parameters
        ----------
        pointgroup : `str`
            Name of the point group to use for 2 face check.
        """

        msg = "!2FACE_CHECK:" + pointgroup
        data = await self.send_msg(msg)
        return data

    async def measure_drift(self, pointgroup):
        """
        Measure drift relative to a nominal point group

        Parameters
        ----------
        pointgroup : `str`
            Name of the point group for drift check.
        """

        msg = "!MEAS_DRIFT:" + pointgroup
        data = await self.send_msg(msg)
        return data

    async def measure_single_point(self, collection, pointgroup, target):
        """
        Point at target, lock on and start measuring target using measurement
        profile

        Parameters
        ----------
        pointgroup : `str`
            Name of the point group that contains the target point.
        target : `str`
            Name of the targe within pointgroup
        """

        msg = f"!MEAS_SINGLE_POINT:{collection};{pointgroup};{target}"
        data = await self.send_msg(msg)
        return data

    async def single_point_measurement_profile(self, profile):
        """
        Not 100% clear what this one does. Just set the profile?

        Parameters
        ----------
        profile : `str`
            Name of the profile, I guess
        """

        msg = "!SINGLE_POINT_MEAS_PROFILE:" + profile
        data = await self.send_msg(msg)
        return data

    async def generate_report(self, reportname):
        """
        Generate report

        Parameters
        ----------
        reportname : `str`
            Name of the report
        """

        msg = "!GEN_REPORT:" + reportname
        data = await self.send_msg(msg)
        return data

    async def set_2face_tolerance(self, tolerance):
        """
        default tolerance is 0.001 dec deg

        Parameters
        ----------
        tolerance : `float`
            (TODO find out what the range is)
        """

        msg = "!SET_2FACE_TOL:" + tolerance
        data = await self.send_msg(msg)
        return data

    async def set_drift_tolerance(self, rms_tol, max_tol):
        """
        rms_tol default 0.050 mm
        max_tol default 0.1 mm

        Parameters
        ----------
        rms_tol : `float`
            rms tolerance
        max_tol : `float`
            max tolerance
        """

        msg = f"!SET_DRIFT_TOL:{rms_tol};{max_tol}"
        data = await self.send_msg(msg)
        return data

    async def set_ls_tolerance(self, rms_tol, max_tol):
        """
        
        not actually sure how this one differs from the previous...

        Parameters
        ----------
        rms_tol : `float`
            rms tolerance
        max_tol : `float`
            max tolerance
        """

        msg = f"!SET_LS_TOL:{rms_tol};{max_tol}"
        data = await self.send_msg(msg)
        return data

    async def load_template_file(self, filepath):
        """
        Load template file

        Parameters
        ----------
        filepath : `str`
            filepath to template file
        """

        msg = "!LOAD_SA_TEMPLATE_FILE;" + filepath
        data = await self.send_msg(msg)
        return data

    async def set_reference_group(self, pointgroup):
        """
        Nominal pt grp to locate station to and provide data relative to.

        Parameters
        ----------
        pointgroup : `str`
            Name of SA Pointgroup to use as reference

        """

        msg = "!SET_REFERENCE_GROUP:" + pointgroup
        data = await self.send_msg(msg)
        return data

    async def set_working_frame(self, workingframe):
        """
        Make workingframe the working frame:

        Parameters
        ----------
        workingframe : `str`
            frame to set as working frame
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

        Parameters
        ----------
        filepath : `str`
            where to save the job file
        """

        msg = "!SAVE_SA_JOBFILE;" + filepath
        data = await self.send_msg(msg)
        return data

    async def set_station_lock(self, station_locked):
        """
        Prevents SA from automatically jumping stations when it detects that
        the tracker has drifted.

        Parameters
        ----------
        locked : `Boolean`
            whether the station locks
        """
        if station_locked:
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

    async def set_telescope_position(self, telalt, telaz, camrot):
        """
        Command in which TCS informs T2SA of the telescope’s current
        position and camera rotation angle, to be used ahead of a
        measurement cmd.
        TODO: we need to add dome position to this for calscreen alignment

        Parameters
        ----------
        telalt : `float`
            altitude of telescope
        telaz : `float`
            azimuth of telescope
        camrot : `float`
            camera rotation
        """

        msg = f"PUBLISH_ALT_AZ_ROT:{telalt};{telaz};{camrot}"
        data = await self.send_msg(msg)
        return data

    async def set_num_samples(self, numsamples):
        """
        This is the number of times the tracker samples each point
        in order to get one (averaged) measurement

        Parameters
        ----------
        numsamples : `int`
            Number of samples
        """

        msg = f"SET_NUM_SAMPLES:{numsamples}"
        data = await self.send_msg(msg)
        return data

    async def set_num_iterations(self, numiters):
        """
        This is the number of times we repeat an auto-measurement
        of a point group

        Parameters
        ----------
        numiters : `Int`
            number of iterations
        """

        msg = f"SET_NUM_ITERATIONS:{numiters}"
        data = await self.send_msg(msg)
        return data

    async def increment_measured_index(self, idx):
        """
        Increment to measured point group index by idx

        Parameters
        ----------
        idx : `Int`
            Index
        """

        msg = f"INC_MEAS_INDEX:{idx}"
        data = await self.send_msg(msg)
        return data
