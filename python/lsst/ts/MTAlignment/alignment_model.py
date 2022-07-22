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
import re
import time
from enum import IntEnum

from lsst.ts import tcpip

from .mock_t2sa import MockT2SA

# Log a warning if it takes longer than this (seconds) to read a reply
LOG_WARNING_TIMEOUT = 5


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
    """Interface to the T2SA low-level controller.

    Parameters
    ----------
    addr : str
        T2SA IP address.
    port : int
        T2SA port.
    read_timeout : float
        Timeout for reading replies to commands (seconds).
    simulation_mode : int
        Simulation mode. One of:

        * 0: normal mode
        * 1: run the T2SA in simulation mode.
        * 2: run a local minimal T2SA simulator.

    log : logging.Logger
        Logger.
    """

    def __init__(self, host, port, read_timeout, simulation_mode, log):
        self.host = host
        self.port = port
        self.read_timeout = read_timeout
        self.simulation_mode = simulation_mode
        self.log = log

        self.reader = None
        self.writer = None
        self.first_measurement = True
        self.t2sa_simulation_mode_set = False
        self.comm_lock = asyncio.Lock()
        self.reply_regex = re.compile(r"(ACK|ERR)-(\d\d\d):? +(.*)")

    async def connect(self):
        """Connect to the T2SA.

        Create a mock T2SA for simulation mode 2.
        """
        if self.simulation_mode == 2:
            self.mock_t2sa = MockT2SA(port=0, log=self.log)
            await self.mock_t2sa.start_task
            self.port = self.mock_t2sa.port
            self.host = tcpip.LOCAL_HOST
            self.log.debug(f"Connecting to mock T2SA at {self.host}:{self.port}")
            t2sa_simulation_mode = 1
        else:
            self.log.debug(f"Connecting to real T2SA at {self.host}:{self.port}")
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
        """Disconnect from the T2SA. A no-op if not connected."""
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
                self.log.debug(f"Wait for ready before sending command {cmd}")
                await self.wait_for_ready()
            return await self._basic_send_command(cmd)

    async def _basic_send_command(self, cmd):
        """Send a command and return the reply, without locking.

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
            t0 = time.monotonic()
            reply_bytes = await asyncio.wait_for(
                self.reader.readuntil(separator=tcpip.TERMINATOR),
                timeout=self.read_timeout,
            )
            dt = time.monotonic() - t0
            if dt > LOG_WARNING_TIMEOUT:
                self.log.warning(
                    f"Took {dt:0.2f} seconds to read {reply_bytes!r} "
                    f"in response to command {cmd_bytes!r}"
                )
            else:
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
        """Query T2SA for status.

        Returns
        -------
        status : str
            May include:

            * READY if tracker is ready
            * 2FACE if executing two-face check
            * DRIFT if executing drift check
            * EMP if executing measurement plan
        """
        return await self.send_command("?STAT")

    async def laser_status(self):
        """Get laser status.

        Returns
        -------
        status : str
            Status may include:

            * LON if laser is on
            * LOFF if laser is off
        """
        return await self.send_command("?LSTA")

    async def laser_on(self):
        """Turn the tracker laser on (to warm it up).

        Returns
        -------
        reply : str
            ACK300 on success
        """
        return await self.send_command("!LST:1")

    async def laser_off(self):
        """Turn the tracker laser off.

        Returns
        -------
        reply : str
            ACK300 on success
        """
        return await self.send_command("!LST:0")

    async def set_simulation_mode(self, simulation_mode):
        """Set the T2SA's simulation mode.

        Parameters
        ----------
        simulation_mode : int
            Simulation mode; must be one of:

            * 0 normal mode
            * 1 simulation mode

        Returns
        -------
        reply : str
            ACK300 on success
        """
        if simulation_mode not in (0, 1):
            raise ValueError(f"simulation_mode={simulation_mode} must be 0 or 1")
        return await self.send_command(f"!SET_SIM:{simulation_mode}")

    async def tracker_off(self):
        """Completely shut down the T2SA.

        Warning: if you issue this command then you must turn
        the T2SA back on manually.

        Returns
        -------
        reply : str
            ACK300 on success
        """
        return await self.send_command("!LST:2")

    async def measure_target(self, target):
        """Execute a measurement plan.

        Parameters
        ----------
        target : str
            Target name, e.g. "M1".

        Returns
        -------
        reply : str
            ACK300 on success
        """
        return await self.send_command(f"!CMDEXE:{target}", wait_for_ready=True)

    async def get_target_position(self, target):
        """Get the position of the specified target.

                You should measure the point using `measure_target`
                before calling this. You may also wish to set the
                current working frame first, by calling `set_working_frame`.

        `        Parameters
                ----------
                target : str
                    Target name, e.g. "M1".

                Returns
                -------
                position : str
                    Position of target, as a point coordinate string,
                    relative to the current working frame.
        """
        return await self.send_command(f"?POS {target}")

    async def get_point_position(self, pointgroup, point, collection="A"):
        """Get the position of a previously measured point.

        Parameters
        ----------
        pointgroup : String
            Name of pointgroup the point is in.
        point : String
            Name of point.
        collection : String
            Name of collection the point is in. Default "A"

        Returns
        -------
        position : str
            Point coordinate string
        """
        return await self.send_command(f"?POINT_POS:{collection};{pointgroup};{point}")

    async def get_target_offset(self, target, reference_pointgroup=None):
        """Get the offset of a target from nominal.

        Parameters
        ----------
        target : str
            Target name, e.g. "M1".
        reference_pointgroup : `None` | `str`
            Name of pointgroup that will be used as the frame of reference for
            the offset. If None then use target.

        Returns
        -------
        position : str
            Offset of target.
        """
        if reference_pointgroup is None:
            reference_pointgroup = target
        return await self.send_command(f"?OFFSET:{reference_pointgroup};{target}")

    async def get_point_delta(
        self, p1group, p1, p2group, p2, p1collection="A", p2collection="A"
    ):
        """Get the offset between two points.

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
        return await self.send_command(
            f"?POINT_DELTA:{p1collection};{p1group};{p1};{p2collection};{p2group};{p2}"
        )

    async def clear_errors(self):
        """
        Clear errors, or return a -300 if we cant clear them
        This may be deprecated soon
        """

        return await self.send_command("!CLERCL")

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
        value = 1 if randomize_points else 0
        return await self.send_command(f"SET_RANDOMIZE_POINTS:{value}")

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
        value = 1 if power_lock else 0
        return await self.send_command(f"SET_POWER_LOCK:{value}")

    async def twoface_check(self, pointgroup):
        """Run the 2 face check against a given point group.

        Parameters
        ----------
        pointgroup : `str`
            Name of the point group to use for 2 face check.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!2FACE_CHECK:{pointgroup}")

    async def measure_drift(self, pointgroup):
        """Measure drift relative to a nominal point group.

        Parameters
        ----------
        pointgroup : `str`
            Name of the point group for drift check.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!MEAS_DRIFT:{pointgroup}")

    async def measure_single_point(self, collection, pointgroup, target):
        """Measure a single point for a specified target.

        Point at the target, lock on, and start measuring the target
        using the measurement profile.

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
        return await self.send_command(
            f"!MEAS_SINGLE_POINT:{collection};{pointgroup};{target}"
        )

    async def single_point_measurement_profile(self, profile):
        """Set a measurement profile in the spatial analyzer.

        Parameters
        ----------
        profile : `str`
            Name of the profile.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!SINGLE_POINT_MEAS_PROFILE:{profile}")

    async def generate_report(self, reportname):
        """Generate a report.

        Parameters
        ----------
        reportname : `str`
            Name of the report

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!GEN_REPORT:{reportname}")

    async def set_twoface_tolerances(self, az_tol, el_tol, range_tol):
        """Set maximum allowed divergences when measuring
        the same point using the tracker's two different "facings".

        Parameters
        ----------
        az_tol : `float`
            Azimuth tolerance (degrees)
        el_tol : `float`
            Elevation tolerance (degrees)
        range_tol : `float`
            Range tolerance (mm)

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!SET_2FACE_TOL:{az_tol};{el_tol};{range_tol}")

    async def set_drift_tolerance(self, rms_tol, max_tol):
        """Set drift tolerance.

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
        return await self.send_command(f"!SET_DRIFT_TOL:{rms_tol};{max_tol}")

    async def set_ls_tolerance(self, rms_tol, max_tol):
        """Set the least-squares tolerance.

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
        return await self.send_command(f"!SET_LS_TOL:{rms_tol};{max_tol}")

    async def load_template_file(self, filepath):
        """Load a template file.

        Parameters
        ----------
        filepath : `str`
            Path of template file

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!LOAD_SA_TEMPLATE_FILE;{filepath}")

    async def set_reference_group(self, pointgroup):
        """Set nominal point group to locate station to and provide
        data relative to.

        Parameters
        ----------
        pointgroup : `str`
            Name of pointgroup.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!SET_REFERENCE_GROUP:{pointgroup}")

    async def set_working_frame(self, workingframe):
        """Set the working frame.

        This is the frame whose coordinate system all coordinates will be
        provided relative to.

        Parameters
        ----------
        workingframe : `str`
            frame to set as working frame

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!SET_WORKING_FRAME:{workingframe}")

    async def new_station(self):
        """Add a new station and make it the active instrument.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!NEW_STATION")

    async def save_sa_jobfile(self, filepath):
        """Save a jobfile

        Parameters
        ----------
        filepath : `str`
            where to save the job file

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!SAVE_SA_JOBFILE;{filepath}")

    async def set_station_lock(self, station_locked):
        """Control whether the spatial analyzer automatically changes stations
        when it detects that the tracker has drifted.

        Parameters
        ----------
        station_locked : `Boolean`
            If True then do not change stations.

        Returns
        -------
        ACK300 or ERR code
        """
        value = 1 if station_locked else 0
        return await self.send_command(f"!SET_STATION_LOCK:{value}")

    async def reset_t2sa(self):
        """Reboot the T2SA and spatial analyzer components.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!RESET_T2SA")

    async def halt(self):
        """Halt the current measurement plan, if any,
        and return to ready state.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!HALT")

    async def set_telescope_position(self, telalt, telaz, camrot):
        """Tell the T2SA the telescope's current position and camera
        rotation angle.

        Issue this command before starting a measurement.

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
        return await self.send_command(f"!PUBLISH_ALT_AZ_ROT:{telalt};{telaz};{camrot}")

    async def set_num_samples(self, numsamples):
        """Set the number of tracker samples per point.

        These samples are averaged to make a single measurement.

        Parameters
        ----------
        numsamples : `int`
            Number of samples

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"SET_NUM_SAMPLES:{numsamples}")

    async def set_num_iterations(self, numiters):
        """Set the number of times to repeat an automatic measurement
        of a point group.

        Parameters
        ----------
        numiters : `Int`
            number of iterations

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"SET_NUM_ITERATIONS:{numiters}")

    async def increment_measured_index(self, inc=1):
        """Set the amount by which to increment the measurement point
        group index.

        Parameters
        ----------
        inc : `Int`
            increment amount

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"INC_MEAS_INDEX:{inc}")

    async def set_measured_index(self, idx):
        """Set the measured point group index.

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
        """Save the current settings.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!SAVE_SETTINGS")

    async def load_tracker_compensation(self, compfile):
        """Load a tracker compensation file

        Parameters
        ----------
        compfile : `String`
            name and  filepath to compensation profile file

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!LOAD_TRACKER_COMPENSATION:{compfile}")
