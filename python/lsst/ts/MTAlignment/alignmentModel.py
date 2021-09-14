import asyncio
from enum import IntEnum
import logging
from lsst.ts.MTAlignment import mockT2sa
from lsst.ts import tcpip


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


class AlignmentModel:
    def __init__(self, host, port, log=logging.getLogger()):
        self.host = host
        self.port = port
        self.log = log
        self.connected = False
        self.reader = None
        self.writer = None
        self.first_measurement = True
        self.simulation_mode = 0
        self.com_lock = asyncio.Lock()
        self.mock_t2sa_ip = "127.0.0.1"
        self.timeout = 10

    async def connect(self):
        """
        Connect to the T2SA host. Spin up a fake one for simulation mode 2.
        """
        if self.simulation_mode == 2:
            self.mock_t2sa = mockT2sa.MockT2SA(port=0)
            self.port = await asyncio.wait_for(self.mock_t2sa.start(), 5)
            self.reader, self.writer = await asyncio.open_connection(
                self.mock_t2sa_ip, self.port
            )
            self.log.debug(f"connected to mock T2SA at {self.mock_t2sa_ip}:{self.port}")
            await self.set_simulation_mode(1) # make sure T2SA is also in sim mode
        else:
            self.log.debug(
                f"attempting to connect to real T2SA at {self.host}:{self.port}"
            )
            self.reader, self.writer = await asyncio.open_connection(
                self.host,
                self.port,
            )
            await self.set_simulation_mode(0)
        self.connected = True

    async def disconnect(self):
        await tcpip.close_stream_writer(self.writer)
        self.connected = False

    async def wait_for_ready(self):
        """
        Checks to see if the tracker is executing a measurement plan.
        If so, hold on to control until we start getting a ready signal
        from the tracker. This is likely to be deprecated later.
        """
        async with self.com_lock:
            wait_states = "EMP\r\n"
            msg = bytes("?STAT\r\n", "ascii")
            self.writer.write(msg)
            await self.writer.drain()
            try:
                data = await self.reader.read(64)
                stat = data.decode()
                if stat == "INIT" or stat == "INIT\r\n":
                    self.log.debug("waiting for init")
                    await asyncio.sleep(5)
                while stat in wait_states:
                    await asyncio.sleep(0.5)
                    self.writer.write(msg)
                    await self.writer.drain()
                    data = await self.reader.read(64)
                    stat = data.decode()
            except (asyncio.IncompleteReadError, ConnectionResetError):
                self.handle_lost_connection()

            await asyncio.sleep(0.5)

    async def handle_lost_connection(self):
        """Called when a connection is closed unexpectedly"""
        pass

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
            msg = bytes(msg, "ascii")
        self.log.debug(f"sending {msg}")
        async with self.com_lock:
            self.writer.write(msg)
            await self.writer.drain()
            self.log.debug(f"sent {msg}")
            try:
                data = await asyncio.wait_for(
                    self.reader.readuntil(separator=bytes("\n", "ascii")),
                    timeout=self.timeout,
                )
            except (asyncio.IncompleteReadError, ConnectionResetError):
                await self.handle_lost_connection()
            self.log.debug(f"Received: {data.decode()!r}")
        return data.decode()

    async def check_status(self):
        """
        query T2SA for status
        Returns
        -------
        READY if tracker is ready
        2FACE if executing two-face check
        DRIFT if executing drift check
        EMP if executing measurement plan
        ERR-xxx if there is an error with error code xxx
        """
        return await self.send_msg("?STAT")

    async def send_string(self, message):
        """
        sends a string

        Parameters
        ----------
        message : `str`
            characters to send to T2SA.
        """
        return await self.send_msg(message)

    async def laser_status(self):
        """
        Query laser tracker's laser status, and update model state accordingly
        Returns
        -------
        LON if laser is on
        LOFF if laser is off
        ERR-xxx if there is an error with error code xxx
        """

        await self.send_msg("?LSTA")

    async def laser_on(self):
        """
        Turns the Tracker Laser on (for warmup purposes)

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_msg("!LST:1")

    async def laser_off(self):
        """
        Turns the Tracker Laser off

        Returns
        -------
        ACK300 or ERR code
        """
        await self.send_msg("!LST:0")

    async def set_simulation_mode(self, sim_mode):
        if sim_mode:
            return await self.send_msg("!SET_SIM:1")
        else:
            return await self.send_msg("!SET_SIM:0")

    async def tracker_off(self):
        """
        Turns the whole tracker off, must be powered back on "manually"

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_msg("!LST:2")

    async def measure_m2(self):
        """
        Execute M2 measurement plan

        Returns
        -------
        ACK300 or ERR code
        """
        self.log.debug("measure m2")
        msg = "!CMDEXE:M2"
        self.log.debug(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        return await self.send_msg(msg)

    async def measure_m1m3(self):
        """
        Execute M1M3 measurement plan

        Returns
        -------
        ACK300 or ERR code
        """
        self.log.debug("measure m1m3")
        msg = "!CMDEXE:M1M3"
        self.log.debug(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        return await self.send_msg(msg)

    async def measure_cam(self):
        """
        Execute Camera measurement plan

        Returns
        -------
        ACK300 or ERR code
        """

        if self.first_measurement:
            self.log.debug("first measurement, waiting for tracker warmup")
            await asyncio.sleep(2)
            self.first_measurement = False
        self.log.debug("measure cam")
        msg = "!CMDEXE:CAM"
        self.log.debug(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        return await self.send_msg(msg)

    async def query_m2_position(self):
        """
        Query M2 position after running the M2 MP
        Position queries are always in terms of M1M3 coordinate frame

        Returns
        -------
        M2 Coordinate String
        """

        self.log.debug("query m2")
        msg = "?POS M2"
        return await self.send_msg(msg)

    async def query_m1m3_position(self):
        """
        Query M1m3 position after running the MP
        Position queries are always in terms of M1M3 coordinate frame

        Returns
        -------
        M1M3 Coordinate String
        """

        self.log.debug("query m1m3")
        msg = "?POS M1M3"
        return await self.send_msg(msg)

    async def query_cam_position(self):
        """
        Query cam position after running the MP
        Position queries are always in terms of M1M3 coordinate frame

        Returns
        -------
        Camera Coordinate String
        """

        self.log.debug("query cam")
        msg = "?POS CAM"
        return await self.send_msg(msg)

    async def query_point_position(self, pointgroup, point, collection="A"):
        """
        Query position of a previously measured point

        Parameters
        ----------
        pointgroup : String
            Name of pointgroup the point is in
        point : String
            Name of point
        collection : String
            name of collection the point is in. Default "A"

        Returns
        -------
        Point Coordiante String
        """
        msg = f"?POINT_POS:{collection};{pointgroup};{point}"
        return await self.send_msg(msg)

    async def query_m2_offset(self, refPtGrp="M1M3"):
        """
        Query M2 offset from nominal

        Parameters
        ----------
        refPtGrp : String
            name of pointgroup that will be used as the frame of reference for
            the offset.

        Returns
        -------
        M2 Offset String
        """

        msg = "?OFFSET:" + refPtGrp + ";M2"
        return await self.send_msg(msg)

    async def query_m1m3_offset(self, refPtGrp="M1M3"):
        """
        Query M1m3 offset from nominal

        Parameters
        ----------
        refPtGrp : String
            name of pointgroup that will be used as the frame of reference for
            the offset.

        Returns
        -------
        M1M3 Offset String
        """

        msg = "?OFFSET:" + refPtGrp + ";M1M3"
        return await self.send_msg(msg)

    async def query_cam_offset(self, refPtGrp="M1M3"):
        """
        Query cam offset from nominal + current rotation

        Parameters
        ----------
        refPtGrp : String
            name of pointgroup that will be used as the frame of reference for
            the offset.

        Returns
        -------
        Camera Offset String
        """

        msg = "?OFFSET:" + refPtGrp + ";CAM"
        return await self.send_msg(msg)

    async def query_point_delta(
        self, p1group, p1, p2group, p2, p1collection="A", p2collection="A"
    ):
        """
        Query delta between two points

        Parameters
        ----------
        p1group : String
            Name of pointgroup the point 1 is in
        p1 : String
            Name of point 1
        p1collection : String
            name of collection point 1 is in. Default "A"
        p2group : String
            Name of pointgroup the point 2 is in
        p2 : String
            Name of point 2
        p2collection : String
            name of collection point 2 is in. Default "A"

        Returns
        -------
        Point Delta or ERR code
        """
        msg = (
            f"?POINT_DELTA:{p1collection};{p1group};{p1};{p2collection};{p2group};{p2}"
        )
        return await self.send_msg(msg)

    async def clear_errors(self):
        """
        Clear errors, or return a -300 if we cant clear them
        This may be deprecated soon
        """

        msg = "!CLERCL"
        return await self.send_msg(msg)

    async def set_randomize_points(self, randomize_points):
        """
        Measure the points in the SpatialAnalyzer database in a random order

        Parameters
        ----------
        randomize_points : Boolean
            True to randomize point order

        Returns
        -------
        ACK300 or ERR code
        """

        if randomize_points == 1:
            msg = "SET_RANDOMIZE_POINTS:1"
        elif randomize_points == 0:
            msg = "SET_RANDOMIZE_POINTS:0"
        else:
            msg = "SET_RANDOMIZE_POINTS:" + str(randomize_points)
        return await self.send_msg(msg)

    async def set_power_lock(self, power_lock):
        """
        enable/disable the Tracker's IR camera which helps it find SMRs, but
        can also cause it to lock on to the wrong one sometimes.

        Parameters
        ----------
        power_lock : Boolean
            True to enable the IR camera assist

        Returns
        -------
        ACK300 or ERR code
        """

        if power_lock:
            msg = "SET_POWER_LOCK:1"
        else:
            msg = "SET_POWER_LOCK:0"
        return await self.send_msg(msg)

    async def twoFace_check(self, pointgroup):
        """
        Runs the 2 face check against a given point group

        Parameters
        ----------
        pointgroup : `str`
            Name of the point group to use for 2 face check.

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!2FACE_CHECK:" + pointgroup
        return await self.send_msg(msg)

    async def measure_drift(self, pointgroup):
        """
        Measure drift relative to a nominal point group

        Parameters
        ----------
        pointgroup : `str`
            Name of the point group for drift check.

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!MEAS_DRIFT:" + pointgroup
        return await self.send_msg(msg)

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

        Returns
        -------
        ACK300 or ERR code
        """

        msg = f"!MEAS_SINGLE_POINT:{collection};{pointgroup};{target}"
        return await self.send_msg(msg)

    async def single_point_measurement_profile(self, profile):
        """
        Sets a measurement profile in SA.

        Parameters
        ----------
        profile : `str`
            Name of the profile.

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!SINGLE_POINT_MEAS_PROFILE:" + profile
        return await self.send_msg(msg)

    async def generate_report(self, reportname):
        """
        Generate report

        Parameters
        ----------
        reportname : `str`
            Name of the report

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!GEN_REPORT:" + reportname
        return await self.send_msg(msg)

    async def set_2face_tolerance(self, az_tol, el_tol, range_tol):
        """
        default tolerance is 0.001 dec deg

        Parameters
        ----------
        az_tol : `float` degrees
        el_tol : `float` degrees
        range_tol : `float` millimeters

        Returns
        -------
        ACK300 or ERR code
        """

        msg = f"!SET_2FACE_TOL:{az_tol};{el_tol};{range_tol}"
        return await self.send_msg(msg)

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

        Returns
        -------
        ACK300 or ERR code
        """

        msg = f"!SET_DRIFT_TOL:{rms_tol};{max_tol}"
        return await self.send_msg(msg)

    async def set_ls_tolerance(self, rms_tol, max_tol):
        """
        sets the least squares tolerance

        Parameters
        ----------
        rms_tol : `float`
            rms tolerance
        max_tol : `float`
            max tolerance

        Returns
        -------
        ACK300 or ERR code
        """

        msg = f"!SET_LS_TOL:{rms_tol};{max_tol}"
        return await self.send_msg(msg)

    async def load_template_file(self, filepath):
        """
        Load template file

        Parameters
        ----------
        filepath : `str`
            filepath to template file

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!LOAD_SA_TEMPLATE_FILE;" + filepath
        return await self.send_msg(msg)

    async def set_reference_group(self, pointgroup):
        """
        Nominal pt grp to locate station to and provide data relative to.

        Parameters
        ----------
        pointgroup : `str`
            Name of SA Pointgroup to use as reference


        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!SET_REFERENCE_GROUP:" + pointgroup
        return await self.send_msg(msg)

    async def set_working_frame(self, workingframe):
        """
        Make workingframe the working frame:
        This is the frame whose coordinate system all coordinates will be
        provided relative to

        Parameters
        ----------
        workingframe : `str`
            frame to set as working frame

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!SET_WORKING_FRAME:" + workingframe
        return await self.send_msg(msg)

    async def new_station(self):
        """
        A new station is added and made to be the active instrument.

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!NEW_STATION"
        return await self.send_msg(msg)

    async def save_sa_jobfile(self, filepath):
        """
        Save a jobfile

        Parameters
        ----------
        filepath : `str`
            where to save the job file

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!SAVE_SA_JOBFILE;" + filepath
        return await self.send_msg(msg)

    async def set_station_lock(self, station_locked):
        """
        Prevents SA from automatically jumping stations when it detects that
        the tracker has drifted.

        Parameters
        ----------
        locked : `Boolean`
            whether the station locks

        Returns
        -------
        ACK300 or ERR code
        """
        if station_locked:
            msg = "!SET_STATION_LOCK:1"
        else:
            msg = "!SET_STATION_LOCK:0"
        return await self.send_msg(msg)

    async def reset_t2sa(self):
        """
        Reboots the T2SA and SA components

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!RESET_T2SA"
        return await self.send_msg(msg)

    async def halt(self):
        """
        Commands T2SA to halt any measurement plans currently executing,
        and return to ready state

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!HALT"
        return await self.send_msg(msg)

    async def set_telescope_position(self, telalt, telaz, camrot):
        """
        Command in which TCS informs T2SA of the telescope’s current
        position and camera rotation angle, to be used ahead of a
        measurement cmd.

        Parameters
        ----------
        telalt : `float`
            altitude of telescope
        telaz : `float`
            azimuth of telescope
        camrot : `float`
            camera rotation

        Returns
        -------
        ACK300 or ERR code
        """

        msg = f"!PUBLISH_ALT_AZ_ROT:{telalt};{telaz};{camrot}"
        return await self.send_msg(msg)

    async def set_num_samples(self, numsamples):
        """
        This is the number of times the tracker samples each point
        in order to get one (averaged) measurement

        Parameters
        ----------
        numsamples : `int`
            Number of samples

        Returns
        -------
        ACK300 or ERR code
        """

        msg = f"SET_NUM_SAMPLES:{numsamples}"
        return await self.send_msg(msg)

    async def set_num_iterations(self, numiters):
        """
        This is the number of times we repeat an auto-measurement
        of a point group

        Parameters
        ----------
        numiters : `Int`
            number of iterations

        Returns
        -------
        ACK300 or ERR code
        """

        msg = f"SET_NUM_ITERATIONS:{numiters}"
        return await self.send_msg(msg)

    async def increment_measured_index(self, inc=1):
        """
        Increment to measured point group index by inc

        Parameters
        ----------
        inc : `Int`
            increment amount

        Returns
        -------
        ACK300 or ERR code
        """

        msg = f"INC_MEAS_INDEX:{inc}"
        return await self.send_msg(msg)

    async def set_measured_index(self, idx):
        """
        Set measured point group index to idx

        Parameters
        ----------
        idx : `Int`
            index

        Returns
        -------
        ACK300 or ERR code
        """

        msg = f"SET_MEAS_INDEX:{idx}"
        return await self.send_msg(msg)

    async def save_settings(self):
        """
        Saves any setting changes immediately. Without calling this, setting
        changes will be applied immediately but will not persist if T2SA
        quits unexpectedly


        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!SAVE_SETTINGS"
        return await self.send_msg(msg)

    async def load_tracker_compensation(self, compfile):
        """
        Loads a tracker compensation file

        Parameters
        ----------
        compfile : `String`
            name and  filepath to compensation profile file

        Returns
        -------
        ACK300 or ERR code
        """

        msg = "!LOAD_TRACKER_COMPENSATION:" + compfile
        return await self.send_msg(msg)
