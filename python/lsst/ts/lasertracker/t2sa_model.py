# This file is part of ts_lasertracker.
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

__all__ = ["LaserStatus", "TrackerStatus", "T2SAError", "T2SAModel"]

import asyncio
import logging
import re
import time
from enum import IntEnum

from lsst.ts import tcpip

from .enums import T2SAErrorCode
from .utils import CartesianCoordinate, parse_offsets, parse_single_point_measurement

# Log a warning if it takes longer than this (seconds) to read a reply
LOG_WARNING_TIMEOUT = 5

# The error code returned by the T2SA if busy, as a string
BUSY_ERR_CODE_STR = str(T2SAErrorCode.CommandRejectedBusy.value)


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
    """Error raised by send_command if the T2SA returns an error.

    Parameters
    ----------
    error_code : `int`
        Error code, which should be a `T2SAErrorCode` value.
        This will be available as an attribute of the same name.
    message : `str`
        Error message.
    """

    def __init__(self, error_code: int, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class T2SAModel:
    """Interface to the T2SA low-level controller.

    Parameters
    ----------
    addr : `str`
        T2SA IP address.
    port : `int`
        T2SA port.
    read_timeout : `float`
        Timeout for reading replies to commands (seconds).
    t2sa_simulation_mode : `bool`
        The T2SA controller has an internal simulation mode. If `True` enable
        simulation mode after establishing a connection.
    log : `logging.Logger`
        Logger.
    """

    def __init__(
        self,
        host: str,
        port: int,
        read_timeout: float,
        t2sa_simulation_mode: bool,
        log: logging.Logger,
    ) -> None:
        self.host = host
        self.port = port
        self.read_timeout = read_timeout
        self.t2sa_simulation_mode = t2sa_simulation_mode
        self.log = log.getChild("T2SAModel")

        self.reader: None | asyncio.StreamReader = None
        self.writer: None | asyncio.StreamWriter = None
        self.first_measurement = True
        self.comm_lock = asyncio.Lock()
        self.reply_regex = re.compile(r"(ACK|ERR)-(\d\d\d) +(.*)")

    async def connect(self) -> None:
        """Connect to the T2SA.

        After the connection is established, set the t2sa simulation mode, this
        is the t2sa controller own simulation mode.
        """
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        await self.set_t2sa_simulation_mode()

    @property
    def connected(self) -> bool:
        """Return True if connected."""
        return not (
            self.reader is None
            or self.writer is None
            or self.reader.at_eof()
            or self.writer.is_closing()
        )

    async def disconnect(self) -> None:
        """Disconnect from the T2SA. A no-op if not connected."""
        if self.writer is not None:
            try:
                await self.reset_t2sa_simulation_mode()
            except Exception:
                self.log.exception("Failed to reset t2sa simulation mode. Ignoring.")
            finally:
                await tcpip.close_stream_writer(self.writer)
                self.writer = None

    async def handle_lost_connection(self) -> None:
        """Handle a connection that is unexpectedly lost."""
        if self.writer is not None:
            await tcpip.close_stream_writer(self.writer)

    async def send_command(self, cmd: str) -> str:
        """Send a command and return the reply.

        Parameters
        ----------
        cmd : `str`
            String message to send to T2SA controller.

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
            return await self._basic_send_command(cmd)

    async def _basic_send_command(self, cmd: str, no_wait_reply: bool = False) -> str:
        """Send a command and return the reply, without locking.

        You must obtain self.comm_lock before calling.
        This exists to support send_command.

        Parameters
        ----------
        cmd : `str`
            Command to write, with no "\r\n" terminator.
        no_wait_reply : `bool`
            Don't wait for reply from the controller.

        Returns
        -------
        reply : `str`
            The reply, with leading "ACK-xxx " and trailing "\r\n" stripped.
        """
        if not self.comm_lock.locked():
            self.log.warning("Communication not locked!")
        if not self.connected:
            raise RuntimeError("Not connected")

        assert self.writer is not None

        cmd_bytes = cmd.encode() + tcpip.TERMINATOR
        self.log.debug(f"Send command {cmd_bytes!r}")
        self.writer.write(cmd_bytes)
        await self.writer.drain()

        if no_wait_reply:
            return ""

        return await self._wait_reply(cmd=cmd)

    async def _wait_reply(self, cmd: str) -> str:
        """Wait for reply from the controller.

        Parameters
        ----------
        cmd : `str`
            Name of the command executed.

        Raises
        ------
        RuntimeError
            If self.comm_lock is not locked, the connection is lost,
            timeout waiting for a reply, or the reply cannot be parsed.
        T2SAError
            If the reply is an error.

        Notes
        -----
        If the code times out while waiting for a reply then the connection
        is closed.
        """
        assert self.reader is not None
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
                    f"in response to command {cmd}"
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
                f"Timed out while waiting for a reply to command {cmd}. "
                f"Read timeout: {self.read_timeout}s. Wait time {time.monotonic()-t0}s."
            )
            self.log.error(err_msg)
            raise RuntimeError(err_msg)

        reply_str = reply_bytes.decode().strip()
        reply_match = self.reply_regex.match(reply_str)
        if reply_match is None:
            raise RuntimeError(f"Cannot parse reply {reply_str!r}")
        reply_type, reply_code, reply_body = reply_match.groups()
        if reply_type == "ACK":
            return reply_body
        else:
            raise T2SAError(error_code=int(reply_code), message=reply_body)

    async def get_status(self) -> str:
        """Query T2SA for status.

        Returns
        -------
        status : `str`
            May include:

            * "READY" if tracker is ready
            * "2FACE" if executing two-face check
            * "DRIFT" if executing drift check
            * "BUSY" if busy

        Notes
        -----
        "BUSY" is not a string returned by the T2SA. Instead, the T2SA
        returns ERR-201, which causes `send_command` to raise an exception.
        This function catches that exception and returns "BUSY".
        """
        try:
            result = await self.send_command("?STAT")  # type: ignore
            if result == "Instrument is connected":
                return "READY"
            else:
                return "BUSY"
        except T2SAError as e:
            if e.error_code in {
                T2SAErrorCode.InstrumentNotReady,
                T2SAErrorCode.CommandRejectedBusy,
            }:
                return "BUSY"
            else:
                raise

    async def laser_status(self) -> str:
        """Get laser status.

        Returns
        -------
        status : `str`
            Status may include:

            * LON if laser is on
            * LOFF if laser is off
        """
        return await self.send_command("?LSTA")

    async def laser_on(self) -> str:
        """Turn the tracker laser on (to warm it up).

        Returns
        -------
        reply : `str`
            ACK300 on success
        """
        return await self.send_command("!LST:1")

    async def laser_off(self) -> str:
        """Turn the tracker laser off.

        Returns
        -------
        reply : `str`
            ACK300 on success
        """
        return await self.send_command("!LST:0")

    async def set_t2sa_simulation_mode(self) -> str:
        """Set the T2SA's simulation mode the appropriate value.

        Returns
        -------
        reply : `str`
            ACK300 on success
        """
        return await self.send_command(f"!SET_SIM:{int(self.t2sa_simulation_mode)}")

    async def reset_t2sa_simulation_mode(self) -> str:
        """Reset T2SA's simulation mode to 0.

        Returns
        -------
        reply : `str`
            ACK300 on success
        """
        return await self.send_command("!SET_SIM:0")

    async def tracker_off(self) -> str:
        """Completely shut down the T2SA.

        Warning: if you issue this command then you must turn
        the T2SA back on manually.

        Returns
        -------
        reply : `str`
            ACK300 on success
        """
        return await self.send_command("!LST:2")

    async def measure_target(self, target: str) -> str:
        """Execute a measurement plan.

        Parameters
        ----------
        target : `str`
            Target name, e.g. "M1".

        Returns
        -------
        reply : `str`
            ACK300 on success
        """
        return await self.send_command(f"!CMDEXE:{target}")

    async def get_target_position(self, target: str) -> dict[str, str | float]:
        """Get the position of the specified target.

        You should measure the point using `measure_target` before calling
        this. You may also wish to set the current working frame first, by
        calling `set_working_frame`.

        Parameters
        ----------
        target : `str`
            Target name, e.g. "M1".

        Returns
        -------
        target_position : `dict` [`str`, `str` | `float`]
            Position of target, as a point coordinate string, relative to the
            current working frame.

        Raises
        ------
        RuntimeError
            If fail to parse response from controller.
        """
        target_position_response = await self.send_command(f"?POS {target}")

        return parse_offsets(target_position_response)

    async def get_point_position(
        self, pointgroup: str, point: str, collection: str = "A"
    ) -> str:
        """Get the position of a previously measured point.

        Parameters
        ----------
        pointgroup : `str`
            Name of pointgroup the point is in.
        point : `str`
            Name of point.
        collection : `str`
            Name of collection the point is in. Default "A"

        Returns
        -------
        position : `str`
            Point coordinate string
        """
        return await self.send_command(f"?POINT_POS:{collection};{pointgroup};{point}")

    async def get_target_offset(
        self, target: str, reference_pointgroup: None | str = None
    ) -> dict[str, str | float]:
        """Get the offset of a target from nominal.

        Parameters
        ----------
        target : `str`
            Target name, e.g. "M1".
        reference_pointgroup : `None` | `str`
            Name of pointgroup that will be used as the frame of reference for
            the offset. If None then use target.

        Returns
        -------
        target_offset : `dict` [`str`, `str` | `float`]
            Target offset information.

        Raise
        -----
        RuntimeError
            If failed to parse response from controller.
        """
        if reference_pointgroup is None:
            reference_pointgroup = target

        target_offset_response = await self.send_command(
            f"?OFFSET:{target};{reference_pointgroup}"
        )

        return parse_offsets(target_offset_response)

    async def get_point_delta(
        self,
        p1group: str,
        p1: str,
        p2group: str,
        p2: str,
        p1collection: str = "A",
        p2collection: str = "A",
    ) -> str:
        """Get the offset between two points.

        Parameters
        ----------
        p1group : `str`
            Name of pointgroup the point 1 is in
        p1 : `str`
            Name of point 1
        p1collection : `str`
            name of collection point 1 is in. Default "A"
        p2group : `str`
            Name of pointgroup the point 2 is in
        p2 : `str`
            Name of point 2
        p2collection : `str`
            name of collection point 2 is in. Default "A"

        Returns
        -------
        Point Delta or ERR code
        """
        return await self.send_command(
            f"?POINT_DELTA:{p1collection};{p1group};{p1};{p2collection};{p2group};{p2}"
        )

    async def clear_errors(self) -> str:
        """Clear errors, or return a -300 if it can not be cleared.

        This may be deprecated soon.
        """
        return await self.send_command("!CLERCL")

    async def set_randomize_points(self, randomize_points: bool) -> str:
        """Measure the points in the SpatialAnalyzer database in a random
        order.

        Parameters
        ----------
        randomize_points : `bool`
            True to randomize point order

        Returns
        -------
        ACK300 or ERR code
        """
        value = 1 if randomize_points else 0
        return await self.send_command(f"SET_RANDOMIZE_POINTS:{value}")

    async def set_power_lock(self, power_lock: bool) -> str:
        """Enable/disable the Tracker's IR camera which helps it find SMRs, but
        can also cause it to lock on to the wrong one sometimes.

        Parameters
        ----------
        power_lock : `bool`
            True to enable the IR camera assist

        Returns
        -------
        ACK300 or ERR code
        """
        value = 1 if power_lock else 0
        return await self.send_command(f"SET_POWER_LOCK:{value}")

    async def twoface_check(self, pointgroup: str) -> str:
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

    async def measure_drift(self, pointgroup: str) -> str:
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

    async def measure_single_point(
        self, collection: str, pointgroup: str, target: str
    ) -> CartesianCoordinate:
        """Measure a single point for a specified target.

        Point at the target, lock on, and start measuring the target
        using the measurement profile.

        Parameters
        ----------
        collection : `str`
            An id for the data collection group.
        pointgroup : `str`
            Name of the point group that contains the target point.
        target : `str`
            Name of the targe within pointgroup

        Returns
        -------
        single_point_measurement : `CartesianCoordinate`
            Single point measurement values in a cartesian coordinate format.

        Raises
        ------
        RuntimeError
            If fail to parse response from controller.
        """
        single_point_response = await self.send_command(
            f"!MEAS_SINGLE_POINT:{collection};{pointgroup};{target}"
        )

        return parse_single_point_measurement(single_point_response)

    async def single_point_measurement_profile(self, profile: str) -> str:
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

    async def generate_report(self, reportname: str) -> str:
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

    async def set_twoface_tolerances(
        self, az_tol: float, el_tol: float, range_tol: float
    ) -> str:
        """Set maximum allowed divergences when measuring the same point using
        the tracker's two different "facings".

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

    async def set_drift_tolerance(self, rms_tol: float, max_tol: float) -> str:
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

    async def set_ls_tolerance(self, rms_tol: float, max_tol: float) -> str:
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

    async def load_template_file(self, filepath: str) -> str:
        """Load a template file.

        Parameters
        ----------
        filepath : `str`
            Path of template file

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!LOAD_SA_TEMPLATE_FILE:{filepath}")

    async def set_reference_group(self, pointgroup: str) -> str:
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

    async def set_working_frame(self, workingframe: str) -> str:
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

    async def new_station(self) -> str:
        """Add a new station and make it the active instrument.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!NEW_STATION")

    async def save_sa_jobfile(self, filepath: str) -> str:
        """Save a jobfile

        Parameters
        ----------
        filepath : `str`
            where to save the job file

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!SAVE_SA_JOBFILE:{filepath}")

    async def set_station_lock(self, station_locked: bool) -> str:
        """Control whether the spatial analyzer automatically changes stations
        when it detects that the tracker has drifted.

        Parameters
        ----------
        station_locked : `bool`
            If True then do not change stations.

        Returns
        -------
        ACK300 or ERR code
        """
        value = 1 if station_locked else 0
        return await self.send_command(f"!SET_STATION_LOCK:{value}")

    async def reset_t2sa(self) -> str:
        """Reboot the T2SA and spatial analyzer components.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!RESET_T2SA")

    async def halt(self) -> str:
        """Halt the current measurement plan, if any,
        and return to ready state.

        Returns
        -------
        ACK300 or ERR code
        """
        await self._basic_send_command("!HALT", no_wait_reply=True)
        async with self.comm_lock:
            return await self._wait_reply(cmd="!HALT")

    async def set_telescope_position(
        self, telalt: float, telaz: float, camrot: float
    ) -> str:
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
        await self.send_command(f"!PUBLISH_ALT_AZ_ROT:{telalt};{telaz};{camrot}")
        await self.send_command(f"!APPLY_ALT_AZ_ROT:{telalt};{telaz};{camrot}")

        return await self.send_command(f"!CMDEXE:CAM_ROT:{telalt};{telaz};{camrot}")

    async def set_num_samples(self, numsamples: int) -> str:
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

    async def set_num_iterations(self, numiters: int) -> str:
        """Set the number of times to repeat an automatic measurement
        of a point group.

        Parameters
        ----------
        numiters : `int`
            number of iterations

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"SET_NUM_ITERATIONS:{numiters}")

    async def increment_measured_index(self, inc: int = 1) -> str:
        """Set the amount by which to increment the measurement point
        group index.

        Parameters
        ----------
        inc : `int`
            Increment amount

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!INC_MEAS_INDEX:{inc}")

    async def set_measured_index(self, idx: int) -> str:
        """Set the measured point group index.

        Parameters
        ----------
        idx : `int`
            Index

        Returns
        -------
        ACK300 or ERR code
        """

        cmd = f"!SET_MEAS_INDEX:{idx}"
        return await self.send_command(cmd)

    async def save_settings(self) -> str:
        """Save the current settings.

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command("!SAVE_SETTINGS")

    async def load_tracker_compensation(self, compfile: str) -> str:
        """Load a tracker compensation file

        Parameters
        ----------
        compfile : `str`
            name and  filepath to compensation profile file

        Returns
        -------
        ACK300 or ERR code
        """
        return await self.send_command(f"!LOAD_TRACKER_COMPENSATION:{compfile}")
