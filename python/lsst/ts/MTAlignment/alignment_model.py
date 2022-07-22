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

__all__ = ["LaserStatus", "TrackerStatus", "T2SAError", "AlignmentModel"]

import asyncio
import logging
import re
from enum import IntEnum

from lsst.ts import tcpip

from .mock_t2sa import MockT2SA

LOCALHOST = "127.0.0.1"


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


class T2SAError(Exception):
    """Error raised by send_command if the T2SA returns an error."""

    def __init__(self, error_code, message):
        super().__init__(message)
        self.error_code = error_code


class AlignmentModel:
    def __init__(self, host, port, simulation_mode=0, log=logging.getLogger()):
        self.host = host
        self.port = port
        self.log = log
        self.reader = None
        self.writer = None
        self.first_measurement = True
        self.simulation_mode = simulation_mode
        self.t2sa_simulation_mode_set = False
        self.comm_lock = asyncio.Lock()
        self.mock_t2sa_ip = "127.0.0.1"
        self.timeout = 30
        self.reply_regex = re.compile(r"(ACK|ERR)-(\d\d\d):? +(.*)")

    async def connect(self):
        """Connect to the T2SA.

        Create a mock T2SA for simulation mode 2.
        """
        if self.simulation_mode == 2:
            self.mock_t2sa = MockT2SA(port=0, log=self.log)
            await self.mock_t2sa.start_task
            self.port = self.mock_t2sa.port
            self.host = LOCALHOST
            self.log.debug(f"Connect to mock T2SA at {self.host}:{self.port}")
            t2sa_simulation_mode = 1
        else:
            self.log.debug(f"Connect to real T2SA at {self.host}:{self.port}")
            t2sa_simulation_mode = 0
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        await self.set_simulation_mode(t2sa_simulation_mode)

    @property
    def connected(self):
        """Return True if connected."""
        return not (
            self.reader is None
            or self.writer is None
            or self.reader.at_eof()
            or self.writer.is_closing()
        )

    async def disconnect(self):
        if self.writer is not None:
            await tcpip.close_stream_writer(self.writer)

    async def wait_for_ready(self):
        """Wait for the tracker to report ready.

        You must obtain self.comm_lock before calling this.

        Check to see if the tracker is executing a measurement plan.
        If so, hold on to the communication lock until we get a ready signal
        from the tracker. This is likely to be deprecated later.

        Raises
        ------
        RuntimeError
            If self.comm_lock is not locked.
            If a reply other than "EMP" (measuring) or "READY" is seen.
        """
        while True:
            reply = await self._basic_send_command("?STAT")
            # Apparently we need to wait an extra 0.5 seconds
            # even if the tracker reports ready.
            # If that is false, move this line to the end of the while block
            await asyncio.sleep(0.5)
            if reply.startswith("READY"):
                return
            # Apparently we ought to only see READY... or EMP
            # but in fact we see many other replies as well,
            # so accept and ignore any OK reply that is not READY...

    async def handle_lost_connection(self):
        """Handle a connection that is unexpectedly lost."""
        if self.writer is not None:
            await tcpip.close_stream_writer(self.writer)

    async def send_command(self, cmd, wait_for_ready=False):
        """Send a command and return the reply.

        Parameters
        ----------
        cmd : `str`
            String message to send to T2SA controller.
        wait_for_ready : `bool`
            If True, wait for the T2SA to be ready before issuing the command.

        Returns
        -------
        reply : `str`
            The reply, with leading "ACK-300 " and trailing "\r\n" stripped.

        Raises
        ------
        RuntimeError
            If the reply cannot be parsed.
        T2SAError
            If the reply is an error.
        """
        async with self.comm_lock:
            if wait_for_ready:
                await self.wait_for_ready()
            return await self._basic_send_command(cmd)

    async def _basic_send_command(self, cmd):
        """Send a command and wait for the reply, without locking.

        You must obtain self.comm_lock before calling.
        This exists to support wait_for_ready and send_command.

        Parameters
        ----------
        cmd : `str`
            Command to write, with no "\r\n" terminator.

        Returns
        -------
        reply : `str`
            The reply, with leading "ACK-300 " and trailing "\r\n" stripped.

        Raises
        ------
        RuntimeError
            If self.comm_lock is not locked, the connection is lost,
            timeout waiting for a reply, or the reply cannot be parsed.
        T2SAError
            If the reply is an error.

        Notes
        -----
        If the reply is a bare "EMP" then that is what is returned.

        If the code times out while waiting for a reply then the connection
        is closed.
        """
        if not self.comm_lock.locked():
            raise RuntimeError("You must obtain the command lock first")
        if not self.connected:
            raise RuntimeError("Not connected")
        cmd_bytes = cmd.encode() + tcpip.TERMINATOR
        self.log.debug(f"Send command {cmd_bytes!r}")
        self.writer.write(cmd_bytes)
        await self.writer.drain()

        try:
            reply_bytes = await asyncio.wait_for(
                self.reader.readuntil(separator=tcpip.TERMINATOR),
                timeout=self.timeout,
            )
            self.log.debug(f"Received reply: {reply_bytes!r}")
        except (asyncio.IncompleteReadError, ConnectionResetError):
            err_msg = f"Connection lost while executing command {cmd}"
            self.log.error(err_msg)
            await self.handle_lost_connection()
            raise RuntimeError(err_msg)
        except asyncio.TimeoutError:
            err_msg = (
                f"Timed out while waiting for a reply to command {cmd}; disconnecting"
            )
            self.log.error(err_msg)
            await self.handle_lost_connection()
            raise RuntimeError(err_msg)

        reply_str = reply_bytes.decode().strip()
        if reply_str == "EMP":
            return reply_str
        reply_match = self.reply_regex.match(reply_str)
        if reply_match is None:
            raise RuntimeError(f"Cannot parse reply {reply_str!r}")
        reply_type, reply_code, reply_body = reply_match.groups()
        if reply_type == "ACK":
            return reply_body
        raise T2SAError(error_code=reply_code, message=reply_body)

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
        return await self.send_command("?STAT")

    async def laser_status(self):
        """
        Query laser tracker's laser status, and update model state accordingly
        Returns
        -------
        LON if laser is on
        LOFF if laser is off
        ERR-xxx if there is an error with error code xxx
        """
        return await self.send_command("?LSTA")

    async def laser_on(self):
        """
        Turns the Tracker Laser on (for warmup purposes)

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!LST:1")

    async def laser_off(self):
        """
        Turns the Tracker Laser off

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!LST:0")

    async def set_simulation_mode(self, sim_mode):
        """Set the T2SA's simulation mode."""
        if sim_mode not in (0, 1):
            raise ValueError(f"sim_mode={sim_mode} must be 0 or 1")
        return await self.send_command(f"!SET_SIM:{sim_mode}")

    async def tracker_off(self):
        """
        Turns the whole tracker off, must be powered back on "manually"

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!LST:2")

    async def measure_m2(self):
        """
        Execute M2 measurement plan

        Returns
        -------
        ACK300 or ERR code
        """
        self.log.debug("measure m2")
        cmd = "!CMDEXE:M2"
        self.log.debug(f"waiting for ready before sending {cmd}")
        return await self.send_command(cmd, wait_for_ready=True)

    async def measure_m1m3(self):
        """
        Execute M1M3 measurement plan

        Returns
        -------
        ACK300 or ERR code
        """
        self.log.debug("measure m1m3")
        cmd = "!CMDEXE:M1M3"
        self.log.debug(f"waiting for ready before sending {cmd}")
        return await self.send_command(cmd, wait_for_ready=True)

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
        cmd = "!CMDEXE:CAM"
        self.log.debug(f"waiting for ready before sending {cmd}")
        return await self.send_command(cmd, wait_for_ready=True)

    async def query_m2_position(self):
        """
        Query M2 position after running the M2 MP
        Position queries are always in terms of M1M3 coordinate frame

        Returns
        -------
        M2 Coordinate String
        """

        self.log.debug("query m2")
        cmd = "?POS M2"
        return await self.send_command(cmd)

    async def query_m1m3_position(self):
        """
        Query M1m3 position after running the MP
        Position queries are always in terms of M1M3 coordinate frame

        Returns
        -------
        M1M3 Coordinate String
        """

        self.log.debug("query m1m3")
        cmd = "?POS M1M3"
        return await self.send_command(cmd)

    async def query_cam_position(self):
        """
        Query cam position after running the MP
        Position queries are always in terms of M1M3 coordinate frame

        Returns
        -------
        Camera Coordinate String
        """

        self.log.debug("query cam")
        cmd = "?POS CAM"
        return await self.send_command(cmd)

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
        cmd = f"?POINT_POS:{collection};{pointgroup};{point}"
        return await self.send_command(cmd)

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

        cmd = "?OFFSET:" + refPtGrp + ";M2"
        return await self.send_command(cmd)

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

        cmd = "?OFFSET:" + refPtGrp + ";M1M3"
        return await self.send_command(cmd)

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

        cmd = "?OFFSET:" + refPtGrp + ";CAM"
        return await self.send_command(cmd)

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
        cmd = (
            f"?POINT_DELTA:{p1collection};{p1group};{p1};{p2collection};{p2group};{p2}"
        )
        return await self.send_command(cmd)

    async def clear_errors(self):
        """
        Clear errors, or return a -300 if we cant clear them
        This may be deprecated soon
        """

        cmd = "!CLERCL"
        return await self.send_command(cmd)

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
            cmd = "SET_RANDOMIZE_POINTS:1"
        elif randomize_points == 0:
            cmd = "SET_RANDOMIZE_POINTS:0"
        else:
            cmd = "SET_RANDOMIZE_POINTS:" + str(randomize_points)
        return await self.send_command(cmd)

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
            cmd = "SET_POWER_LOCK:1"
        else:
            cmd = "SET_POWER_LOCK:0"
        return await self.send_command(cmd)

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

        cmd = "!2FACE_CHECK:" + pointgroup
        return await self.send_command(cmd)

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

        cmd = "!MEAS_DRIFT:" + pointgroup
        return await self.send_command(cmd)

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

        cmd = f"!MEAS_SINGLE_POINT:{collection};{pointgroup};{target}"
        return await self.send_command(cmd)

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

        cmd = "!SINGLE_POINT_MEAS_PROFILE:" + profile
        return await self.send_command(cmd)

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

        cmd = "!GEN_REPORT:" + reportname
        return await self.send_command(cmd)

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

        cmd = f"!SET_2FACE_TOL:{az_tol};{el_tol};{range_tol}"
        return await self.send_command(cmd)

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

        cmd = f"!SET_DRIFT_TOL:{rms_tol};{max_tol}"
        return await self.send_command(cmd)

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

        cmd = f"!SET_LS_TOL:{rms_tol};{max_tol}"
        return await self.send_command(cmd)

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

        cmd = "!LOAD_SA_TEMPLATE_FILE;" + filepath
        return await self.send_command(cmd)

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

        cmd = "!SET_REFERENCE_GROUP:" + pointgroup
        return await self.send_command(cmd)

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

        cmd = "!SET_WORKING_FRAME:" + workingframe
        return await self.send_command(cmd)

    async def new_station(self):
        """
        A new station is added and made to be the active instrument.

        Returns
        -------
        ACK300 or ERR code
        """

        cmd = "!NEW_STATION"
        return await self.send_command(cmd)

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

        cmd = "!SAVE_SA_JOBFILE;" + filepath
        return await self.send_command(cmd)

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
            cmd = "!SET_STATION_LOCK:1"
        else:
            cmd = "!SET_STATION_LOCK:0"
        return await self.send_command(cmd)

    async def reset_t2sa(self):
        """
        Reboots the T2SA and SA components

        Returns
        -------
        ACK300 or ERR code
        """

        cmd = "!RESET_T2SA"
        return await self.send_command(cmd)

    async def halt(self):
        """
        Commands T2SA to halt any measurement plans currently executing,
        and return to ready state

        Returns
        -------
        ACK300 or ERR code
        """

        cmd = "!HALT"
        return await self.send_command(cmd)

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

        cmd = f"!PUBLISH_ALT_AZ_ROT:{telalt};{telaz};{camrot}"
        return await self.send_command(cmd)

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

        cmd = f"SET_NUM_SAMPLES:{numsamples}"
        return await self.send_command(cmd)

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

        cmd = f"SET_NUM_ITERATIONS:{numiters}"
        return await self.send_command(cmd)

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

        cmd = f"INC_MEAS_INDEX:{inc}"
        return await self.send_command(cmd)

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

        cmd = f"SET_MEAS_INDEX:{idx}"
        return await self.send_command(cmd)

    async def save_settings(self):
        """
        Saves any setting changes immediately. Without calling this, setting
        changes will be applied immediately but will not persist if T2SA
        quits unexpectedly


        Returns
        -------
        ACK300 or ERR code
        """

        cmd = "!SAVE_SETTINGS"
        return await self.send_command(cmd)

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

        cmd = "!LOAD_TRACKER_COMPENSATION:" + compfile
        return await self.send_command(cmd)
