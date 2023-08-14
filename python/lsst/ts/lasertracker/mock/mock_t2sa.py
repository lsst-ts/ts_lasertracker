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

__all__ = ["MockT2SA"]

import asyncio
import logging
import re
import typing

from lsst.ts import tcpip, utils

from ..enums import T2SAErrorCode
from ..utils import MEASURE_REGEX
from .mock_utils import OPTIMAL_POSITION, TelescopePosition, get_random_initial_position

# Good reply bodies. They should come after the initial "ACK-300 " in replies,
# and thus are intended as arguments to `write_good_reply`.
ALREADY_MEASURING_REPLY = "ACK000"
OK_REPLY = "ACK300"  # Command was accepted
T2SA_STATUS_READY = "READY"
T2SA_REPLY_READY = "READY"

# Special status string for busy; may be any reasonable value
# that does not match a non-busy status.
BUSY_STATUS = "_BUSY_"


class MockT2SA(tcpip.OneClientServer):
    """Emulate a New River Kinematics T2SA application.

    This emulator relies on a circular body representation of each individual
    "point group" in the T2SA application to provide realistic measurements.

    Responses to messages sent by the client are parsed using a regular
    expression and used to call appropriate methods do handle the responses.
    In few cases the mock relies on a simple canned response.

    Parameters
    ----------
    host : `str` or `None`
        IP address for this server; typically `LOCAL_HOST`
    port : `int`
        IP port for this server. If 0 then randomly pick an available port
        (or ports, if listening on multiple sockets).
        0 is strongly recommended for unit tests.
    log : `logging.Logger`
        Logger; if None create a new one.

    Attributes
    ----------
    host : `str` or `None`
        IP address for this server; typically `LOCAL_HOST`
    port : `int`
        IP port for this server. If this mock was constructed with port=0
        then this will be the assigned port, once `start` is done.
    """

    def __init__(
        self,
        log: logging.Logger,
        host: str = tcpip.LOCAL_HOST,
        port: int = 0,
    ) -> None:
        self.measure_task = utils.make_done_future()
        self.reply_loop_task = utils.make_done_future()

        self.laser_warmup_task: asyncio.Task = utils.make_done_future()

        self.canned_replies = {
            "!SET_SIM:0": "ACK300",
            "!SET_SIM:1": "ACK300",
            "SET_RANDOMIZE_POINTS:0": "ACK300",
            "SET_RANDOMIZE_POINTS:1": "ACK300",
            "!RESET_T2SA": "ACK300",
            "!NEW_STATION": "ACK300",
        }

        self.dispatchers: dict[str, tuple[typing.Any, re.Pattern]] = {
            name: (method, re.compile(regex_str))
            for name, method, regex_str in (
                ("!2FACE_CHECK", self.execute_two_face_check, r"(?P<point_group>.*)"),
                ("!CMDEXE", self.execute_measure_plan, r"(?P<point_group>.*)"),
                ("!HALT", self.execute_halt, ""),
                (
                    "!LOAD_SA_TEMPLATE_FILE",
                    self.execute_load_sa_template_file,
                    r"(?P<file_path>.*)",
                ),
                ("!LST", self.execute_set_power, r"(?P<value>.*)"),
                ("!MEAS_DRIFT", self.execute_drift, r"(?P<point_group>.*)"),
                (
                    "!MEAS_SINGLE_POINT",
                    self.execute_measure_single_point,
                    r"(?P<collection>.*);(?P<point_group>.*);(?P<point_n>.*)",
                ),
                (
                    "!PUBLISH_ALT_AZ_ROT",
                    self.execute_set_alt_az_rot,
                    r"(?P<alt>.*);(?P<az>.*);(?P<rot>.*)",
                ),
                ("!SAVE_SA_JOBFILE", self.execute_save_sa_jobfile, r"(?P<filename>.*)"),
                (
                    "!SET_REFERENCE_GROUP",
                    self.execute_set_reference_group,
                    r"(?P<reference_group>.*)",
                ),
                (
                    "!SET_WORKING_FRAME",
                    self.execute_set_working_frame,
                    r"(?P<working_frame>.*)",
                ),
                ("?LSTA", self.execute_get_laser_status, ""),
                (
                    "?OFFSET",
                    self.execute_write_point_group_offset,
                    r"(?P<point_group>.*);(?P<reference_group>.*)",
                ),
                (
                    "?POINT_DELTA",
                    self.execute_measure_point_delta,
                    r"(?P<p1collection>.*);(?P<p1group>.*);(?P<p1>.*);"
                    r"(?P<p2collection>.*);(?P<p2group>.*);(?P<p2>.*)",
                ),
                (
                    "?POS",
                    self.execute_write_point_group_position,
                    r"(?P<point_group>.*)",
                ),
                ("?STAT", self.execute_write_status, ""),
            )
        }

        self.collection_point_regexp = re.compile(r"(?P<group>.*)_P(?P<index>.*)")

        duplicate_keys = self.dispatchers.keys() & self.canned_replies.keys()
        if duplicate_keys:
            raise RuntimeError(
                f"Bug: keys {duplicate_keys} appear in both "
                "canned_replies and command_handlers"
            )

        self._laser_warmup_start_tai: None | float = None
        self._reference_group = "M1M3"
        # TODO: Get valid working frame values.
        self.valid_working_frame = {""}
        # TODO: Get good default working frame value.
        self.working_frame = ""
        self.laser_status = "LOFF"
        self.laser_warmup_time = 60.0

        self.t2sa_status = T2SA_STATUS_READY

        # How long to wait while pretending to measure (seconds)
        self.measurement_duration = 2.0

        self.position_optimum = OPTIMAL_POSITION

        self.position_current = get_random_initial_position()

        self._telescope_position = TelescopePosition()

        self._commands_reply_tasks: list[asyncio.Task] = []

        super().__init__(
            name="MockT2SA",
            host=host,
            port=port,
            connect_callback=self.run_reply_loop,
            log=log,
        )

    @property
    def reference_frame(self) -> str:
        """Get the reference frame, formatted for output."""
        return f"FRAME{self._reference_group}"

    def is_measuring(self) -> bool:
        """Is t2sa executing a measurement?

        Returns
        -------
        `bool`
            True if there is an ongoing measurement.
        """
        return not self.measure_task.done()

    def is_ready(self) -> bool:
        """Determine is T2SA is ready for performing activities.

        Returns
        -------
        `bool`
            True if ready, False otherwise.
        """
        return self.laser_status == "LON" and self.laser_warmup_task.done()

    def get_readiness_status(self) -> str:
        """Get readiness status.

        Returns
        -------
        `str`
            A human readable string with the readiness status.
        """
        if self.laser_status != "LON":
            return f"Laser status {self.laser_status}. Should be 'LON'."
        else:
            return T2SA_REPLY_READY

    async def execute_drift(self, point_group: str) -> None:
        """Simulate a drift measurement.

        Parameters
        ----------
        point_group : `str`
            Point group to execute drift measurements (e.g. M1M3, M2, CAM).
        """
        try:
            await self._execute_action("DRIFT", point_group)
        except Exception:
            self.log.exception("Error execution action.")
        else:
            await self._write_reply(
                f"ACK-106 Successfully ran drift scan for {point_group}"
            )

    async def execute_two_face_check(self, point_group: str) -> None:
        """Simulate a two face check.

        Parameters
        ----------
        point_group : `str`
            Point group to execute 2 face check (e.g. M1M3, M2, CAM).
        """
        try:
            await self._execute_action("2FACE", point_group)
        except Exception:
            self.log.exception("Error execution action.")
        else:
            await self._write_reply(
                f"ACK-106 Successfully ran two face check for {point_group}"
            )

    async def execute_measure_plan(self, point_group: str) -> None:
        """Simulate a measurement plan.

        Acknowledge the request to measure, then pretend to measure.

        Parameters
        ----------
        point_group : `str`
            Point group to measure (e.g. M1M3, M2, CAM).
        """
        try:
            self.log.debug(f"Executing measurement plan for {point_group=}.")
            await self._execute_action(BUSY_STATUS, point_group)
        except Exception:
            self.log.exception("Error execution action.")
        else:
            self.log.debug(
                f"Measurement plan for {point_group=} completed successfully."
            )
            await self._write_reply(f"ACK-106 Successfully ran CMD {point_group}")

    async def execute_halt(self) -> None:
        """Halt any ongoing measurement."""
        if not self.measure_task.done():
            self.log.debug("Measure task running, cancelling it.")
            self.measure_task.cancel()
        await asyncio.sleep(0.5)
        self.t2sa_status = T2SA_STATUS_READY
        await self.write_good_reply(self.t2sa_status)

    async def execute_load_sa_template_file(self, file_path: str) -> None:
        """Simulate loading an SA Template File.

        Parameters
        ----------
        file_path : `str`
            Path of the file in the SA node.
        """

        sa_template_dir = r"C:\\Program Files (x86)\\New River Kinematics\\T2SA\\"

        if file_path.startswith(sa_template_dir) and file_path.endswith(".xit64"):
            await self.write_good_reply(T2SA_REPLY_READY)
        else:
            await self.write_error_reply(
                T2SAErrorCode.SATemplateFileNotFound,
                "SA Template file not found or loaded.",
            )

    async def _execute_action(self, action: str, point_group: str) -> None:
        """Simulate a certain action.

        Parameters
        ----------
        action : `str`
            Name of the action.
        point_group : `str`
            Point group the action is being executed for.
        """
        self.log.debug(f"Executing {action} for {point_group}.")

        # Schedule task that will emulate measurement in the background
        if not self.measure_task.done():
            await self.write_error_reply(
                T2SAErrorCode.CommandRejected,
                "Ongoing measurement.",
            )
            raise RuntimeError("Ongoing measurement target.")
        elif not self.is_ready():
            await self.write_error_reply(
                T2SAErrorCode.CommandRejected,
                f"T2SA not ready: {self.get_readiness_status()}.",
            )
            raise RuntimeError(f"T2SA not ready: {self.get_readiness_status()}.")
        elif point_group.lower() not in self.position_optimum:
            await self.write_error_reply(
                T2SAErrorCode.DidFindOrSetPointGroupAndTargetName,
                f"No point group {point_group}.",
            )
            raise RuntimeError(f"No point group {point_group}.")
        else:
            self.t2sa_status = action
            self.measure_task = asyncio.create_task(self.measure())
            self.log.debug("Waiting for measure task to complete.")
            try:
                await self.measure_task
            except asyncio.CancelledError:
                await self.write_error_reply(
                    code=T2SAErrorCode.CommandToHaltT2SASucceeded,
                    reply=f"Error executing measure plan for {point_group}",
                )
                raise RuntimeError("Measure task cancelled!")
            else:
                self.log.debug("Measure task completed.")

    async def execute_write_status(self) -> None:
        """Write current status."""

        if self.t2sa_status == BUSY_STATUS:
            await self.write_error_reply(
                T2SAErrorCode.CommandRejectedBusy, "Command rejected. SA is busy."
            )
        else:
            await self.write_good_reply(self.t2sa_status)

    async def execute_write_point_group_position(self, point_group: str) -> None:
        """Write the position of a point group.

        Parameters
        ----------
        point_group : `str`
            Name of the point group.
        """
        target = MEASURE_REGEX.match(point_group)

        if target is None:
            await self.write_error_reply(
                T2SAErrorCode.DidFindOrSetPointGroupAndTargetName,
                f"No point group {point_group}.",
            )
        else:
            await self.write_point_group_position(target.groupdict()["target"])

    async def execute_write_point_group_position_m1m3(self) -> None:
        """Write the point group position for m1m3."""
        await self.write_point_group_position("m1m3")

    async def execute_write_point_group_position_m2(self) -> None:
        """Write the point group position for m2."""
        await self.write_point_group_position("m2")

    async def execute_write_point_group_position_cam(self) -> None:
        """Write the point group position for camera."""
        await self.write_point_group_position("cam")

    async def write_point_group_position(self, point_group: str) -> None:
        """Write the input point group position.

        Parameters
        ----------
        point_group : `str`
            Name of the point group.
        """

        if self.is_measuring():
            await self.write_error_reply(
                T2SAErrorCode.CommandRejected, "Command rejected. SA is busy."
            )
        elif self.measure_task.cancelled():
            await self.write_error_reply(
                T2SAErrorCode.FailedPointGroupMeasurement, "Measurement failed."
            )
        else:
            point_group_name = point_group.lower()
            if point_group_name not in self.position_current:
                await self.write_error_reply(
                    T2SAErrorCode.DidFindOrSetPointGroupAndTargetName,
                    f"No point group {point_group_name}.",
                )
            else:
                await self._write_position(body_name=point_group_name)

    async def execute_write_point_group_offset(
        self, reference_group: str, point_group: str
    ) -> None:
        """Write a point group offset.

        Parameters
        ----------
        reference_group : `str`
            Which "point group" to use as a reference (e.g. M1M3, M2, CAM).
        point_group : `str`
            Which "point group" to get offset for (e.g. M1M3, M2, CAM).
        """
        reference_group_match = MEASURE_REGEX.match(reference_group)
        point_group_match = MEASURE_REGEX.match(point_group)
        if (
            reference_group_match is None
            or reference_group_match.groupdict()["target"].lower()
            not in self.position_optimum
        ):
            await self.write_error_reply(
                T2SAErrorCode.DidFindOrSetPointGroupAndTargetName,
                f"No reference point group {reference_group}.",
            )
        elif (
            point_group_match is None
            or point_group_match.groupdict()["target"].lower()
            not in self.position_current
        ):
            await self.write_error_reply(
                T2SAErrorCode.DidFindOrSetPointGroupAndTargetName,
                f"No point group {point_group}.",
            )
        else:
            await self._write_offset(
                reference_group=reference_group_match.groupdict()["target"].lower(),
                point_group=point_group_match.groupdict()["target"].lower(),
            )

    async def execute_measure_point_delta(
        self,
        p1collection: str,
        p1group: str,
        p1: str,
        p2collection: str,
        p2group: str,
        p2: str,
    ) -> None:
        """Get the offset between two points.

        Parameters
        ----------
        p1collection : `str`
            Name of point group the point 1 is in.
        p1group : `str`
            Name of point 1.
        p1 : `str`
            name of collection point 1 is in.
        p2collection : `str`
            Name of point group the point 2 is in.
        p2group : `str`
            Name of point 2.
        p2 : `str`
            name of collection point 2 is in..
        """
        # Note: I am not really sure what this method does. It seems like it
        # reads previously made measurements and compute the offset between
        # them. I am simply going to emulate that without trying to keep track
        # about collections and pre-existing measurements.

        if p1group.lower() not in self.position_current:
            await self.write_error_reply(
                T2SAErrorCode.DidFindOrSetPointGroupAndTargetName, f"No group {p1group}"
            )
            return

        if p2group.lower() not in self.position_current:
            await self.write_error_reply(
                T2SAErrorCode.DidFindOrSetPointGroupAndTargetName, f"No group {p2group}"
            )
            return

        p1_index, error_message = self.parse_collection_point(
            point_name=p1, group=p1group
        )

        if error_message:
            await self.write_error_reply(
                T2SAErrorCode.FailedPointGroupMeasurement, error_message
            )
            return

        p2_index, error_message = self.parse_collection_point(
            point_name=p2, group=p2group
        )

        if error_message:
            await self.write_error_reply(
                T2SAErrorCode.FailedPointGroupMeasurement, error_message
            )
            return

        p1_position = self.position_current[p1group.lower()].get_one_fiducial_position(
            p1_index
        )
        p2_position = self.position_current[p2group.lower()].get_one_fiducial_position(
            p2_index
        )

        await self.write_good_reply(
            f"Single Point Measurement {p2} result "
            f"{p2_position.x-p1_position.x},"
            f"{p2_position.y-p1_position.y},"
            f"{p2_position.z-p1_position.z} "
            f"{self._get_time_str()} False"
        )

    def parse_collection_point(self, point_name: str, group: str) -> tuple[int, str]:
        """Parse collection point.

        Parameters
        ----------
        point_name : str
            Name of the point.
        group : str
            Name of the group the point belongs to.

        Returns
        -------
        index : `int`
            Index of the point in the group, from 0 to N-1.
        error_message : `str`
            Error message from parsing the point name. Empty if no error.
        """
        try:
            collection_point_match = self.collection_point_regexp.match(point_name)
            assert collection_point_match is not None

            collection_point = collection_point_match.groupdict()
            assert collection_point["group"] == group

            index = int(collection_point["index"])

            assert (
                1
                <= index
                <= self.position_current[group.lower()].get_number_of_fiducial()
            )
            return index - 1, ""
        except Exception as e:
            return 0, (
                f"Unable to parse p1={point_name}. Must be in the format {group}_N, "
                f"where N goes from 1 to {self.position_current[group.lower()].get_number_of_fiducial()}. "
                f"Exception: {e}."
            )

    async def execute_get_laser_status(self) -> None:
        """Write laser status."""
        if self.laser_status == "WARM":
            assert self._laser_warmup_start_tai is not None
            remaining_warmup_time = utils.current_tai() - self._laser_warmup_start_tai
            await self.write_good_reply(f"WARM, {remaining_warmup_time:.2f} seconds")
        else:
            await self.write_good_reply(self.laser_status)

    async def execute_measure_single_point(
        self, collection: str, point_group: str, point_n: str
    ) -> None:
        """Measure a single point.

        Parameters
        ----------
        collection : `str`
            An identifier to group this measurement internally.
        point_group : `str`
            Which group to measure (e.g. M1M3, M2, CAM).
        point_n : `str`
            A string representation of which point from the group to measure.
            The format is <point_group>_<index>, where index is the 1-based
            index of the point in the group.
        """

        if not self.is_ready():
            await self.write_error_reply(
                T2SAErrorCode.CommandRejected,
                f"T2SA not ready: {self.get_readiness_status()}.",
            )
            return

        point_id = int(point_n.split("_")[-1]) - 1
        point_position = self.position_current[
            point_group.lower()
        ].get_one_fiducial_position(fiducial=point_id)

        await self.write_good_reply(
            f"Single Point Measurement {point_n} result "
            f"{point_position.x*1e3:.6f},"
            f"{point_position.y*1e3:.6f},"
            f"{point_position.z*1e3:.6f} "
            f"{self._get_time_str()} True"
        )

    async def execute_set_alt_az_rot(self, alt: str, az: str, rot: str) -> None:
        """Set alt/az/rot values.

        Parameters
        ----------
        alt : `str`
            Altitude in deg. Value will be used to cast a `float`.
        az : `str`
            Azimuth in deg. Value will be used to cast a `float`.
        rot : `str`
            Rotator angle in deg. Value will be used to cast a `float`.
        """
        try:
            self._telescope_position.elevation = float(alt)
            self._telescope_position.azimuth = float(az)
            self._telescope_position.rotator = float(rot)
            await self.write_good_reply(T2SA_REPLY_READY)
        except ValueError:
            await self.write_error_reply(
                T2SAErrorCode.CommandRejected,
                f"Failed to convert a value to float: {alt}/{az}/{rot}.",
            )
        except Exception as e:
            await self.write_error_reply(T2SAErrorCode.CommandRejected, f"Error: {e}")

    async def execute_save_sa_jobfile(self, filename: str) -> None:
        """Simulate saving an SA job file.

        Parameters
        ----------
        filename : `str`
            Name of the file must match a Windows path, e.g. C:.
        """

        if filename.startswith("C:"):
            await self.write_good_reply(T2SA_REPLY_READY)
        else:
            await self.write_error_reply(
                T2SAErrorCode.SaveSAJobFileFailed, "Save SA job file failed."
            )

    async def execute_set_reference_group(self, reference_group: str) -> None:
        """Set the reference point group.

        Parameters
        ----------
        reference_group : `str`
            New reference group.
        """

        if reference_group.lower() not in self.position_optimum:
            await self.write_error_reply(
                T2SAErrorCode.RefGroupNotFoundInTemplateFile,
                f"No group {reference_group}. Must be one of {self.position_optimum.keys()}.",
            )
        else:
            self._reference_group = reference_group
            await self.write_good_reply(T2SA_REPLY_READY)

    async def execute_set_working_frame(self, working_frame: str) -> None:
        """Set the working frame.

        This is the frame whose coordinate system all coordinates will be
        provided relative to.

        Parameters
        ----------
        working_frame : str
            New value of the working frame.
        """

        if working_frame not in self.valid_working_frame:
            await self.write_error_reply(
                T2SAErrorCode.WorkingFrameNotFound, "POS: NotFound"
            )
        else:
            self.working_frame = working_frame
            await self.write_good_reply(T2SA_REPLY_READY)

    async def execute_set_power(self, value: str) -> None:
        """Set power on or off.

        Parameters
        ----------
        power : `str`
            The input argument passed to the execution; one of:

            * "0": power off
            * "1": power on and execute warmup procedure.
        """

        if value == "0":
            await self.power_off()
        elif value == "1":
            await self.power_on()
        else:
            await self.write_error_reply(
                T2SAErrorCode.CommandRejected, f"Invalid input argument: {value}."
            )

    async def power_off(self) -> None:
        """Set power off."""
        self.laser_status = "LOFF"
        await self.write_good_reply("Tracker Interface Stopped: True")

    async def power_on(self) -> None:
        """Set power on and execute warming sequence."""
        self.laser_status = "WARM"
        self.laser_warmup_task = asyncio.create_task(self._warmup_laser())
        await self.write_good_reply("Tracker Interface Started: True")

    async def _write_position(self, body_name: str) -> None:
        """Write a position.

        Parameters
        ----------
        body_name : `str`
            Name of the body to get position.
        """
        body = self.position_current[body_name]

        await self.write_good_reply(
            f"Object Offset Report Frame{body_name.upper()}_{self._get_measurement_id()};"
            f"X:{body.origin.x};"
            f"Y:{body.origin.y};"
            f"Z:{body.origin.z};"
            f"Rx:{body.rotation.u};"
            f"Ry:{body.rotation.v};"
            f"Rz:{body.rotation.w};"
            f"{self._get_time_str()}"
        )

    def run_reply_loop(self, server: tcpip.OneClientServer) -> None:
        """Halt and possibly restart `reply_loop`.

        Called when a client connects or disconnects.

        Parameters
        ----------
        server : `tcpip.OneClientServer`
            Instance of the server.
        """
        self.reply_loop_task.cancel()
        if self.connected:
            self.reply_loop_task = asyncio.create_task(self.reply_loop())

    async def reply_loop(self) -> None:
        """Listen for commands and issue replies."""

        self.log.debug("reply loop begins")
        try:
            while self.connected:
                command_bytes = await self.reader.readline()
                self.log.debug(f"Mock T2SA received command: {command_bytes}")
                if not command_bytes:
                    self.log.info(
                        "read loop ending; null data read indicates client hung up"
                    )
                    break

                command = command_bytes.decode().strip()
                if not command:
                    continue

                self._commands_reply_tasks.append(
                    asyncio.create_task(self._handle_comand(command))
                )

                done_tasks_index = [
                    i
                    for i, task in enumerate(self._commands_reply_tasks)
                    if task.done()
                ]

                for index in done_tasks_index:
                    await self._commands_reply_tasks.pop(index)
        except asyncio.CancelledError:
            pass
        except (asyncio.IncompleteReadError, ConnectionResetError):
            self.log.info("reply loop ending; connection lost")
        except Exception:
            self.log.exception("reply loop failed")
        self.log.debug("reply loop ends")
        asyncio.create_task(self.close_client())

    async def measure(self) -> None:
        """Emulate measurement plan."""
        self.log.debug("start pretending to measure")
        await asyncio.sleep(self.measurement_duration)
        self.t2sa_status = T2SA_STATUS_READY
        self.log.debug("stop pretending to measure")

    async def write_good_reply(self, reply: str) -> None:
        r"""Write a good reply to the client, prefixed with "ACK-300 "

        Parameters
        ----------
        reply : `str`
            The reply (without a leading "ACK-xxx " or trailing "\\r\\n".
        """
        await self._write_reply(f"ACK-300 {reply}")

    async def write_error_reply(self, code: T2SAErrorCode, reply: str) -> None:
        r"""Write an error reply to the client, prefixed with "ERR-xxx ".

        Parameters
        ----------
        code : `T2SAErrorCode`
            The error code.
        reply : `str`
            The reply (without a leading "ERR-xxx " or trailing "\\r\\n".
        """
        code = T2SAErrorCode(code)
        await self._write_reply(f"ERR-{code} {reply}")

    async def _write_offset(self, reference_group: str, point_group: str) -> None:
        """Write offset.

        Parameters
        ----------
        reference_group : `str`
            Reference group for the offset.
        point_group : `str`
            Point group to compute offset for.
        """

        position_optimum_reference = self.position_optimum[reference_group]
        position_optimum_point_group = self.position_optimum[point_group]

        origin_x = (
            position_optimum_point_group.origin.x - position_optimum_reference.origin.x
        )
        origin_y = (
            position_optimum_point_group.origin.y - position_optimum_reference.origin.y
        )
        origin_z = (
            position_optimum_point_group.origin.z - position_optimum_reference.origin.z
        )
        origin_u = (
            position_optimum_point_group.rotation.u
            - position_optimum_reference.rotation.u
        )
        origin_v = (
            position_optimum_point_group.rotation.v
            - position_optimum_reference.rotation.v
        )
        origin_w = (
            position_optimum_point_group.rotation.w
            - position_optimum_reference.rotation.w
        )

        position_reference = self.position_current[reference_group]
        position_point_group = self.position_current[point_group]

        dx = position_point_group.origin.x - position_reference.origin.x
        dy = position_point_group.origin.y - position_reference.origin.y
        dz = position_point_group.origin.z - position_reference.origin.z
        du = position_point_group.rotation.u - position_reference.rotation.u
        dv = position_point_group.rotation.v - position_reference.rotation.v
        dw = position_point_group.rotation.w - position_reference.rotation.w

        await self.write_good_reply(
            f"Object Offset Report Frame{point_group.upper()}_{self._get_measurement_id()};"
            f"X:{dx-origin_x};"
            f"Y:{dy-origin_y};"
            f"Z:{dz-origin_z};"
            f"Rx:{du-origin_u};"
            f"Ry:{dv-origin_v};"
            f"Rz:{dw-origin_w};"
            f"{self._get_time_str()}"
        )

        # Assume that when someone reads the offset, they correct for it, so
        # bring the reference position close to the optimum position.
        position_reference.origin.x = (
            position_reference.origin.x + position_optimum_point_group.origin.x
        ) / 2.0
        position_reference.origin.y = (
            position_reference.origin.y + position_optimum_point_group.origin.y
        ) / 2.0
        position_reference.origin.z = (
            position_reference.origin.z + position_optimum_point_group.origin.z
        ) / 2.0
        position_reference.rotation.u = (
            position_reference.rotation.u + position_optimum_point_group.rotation.u
        ) / 2.0
        position_reference.rotation.v = (
            position_reference.rotation.v + position_optimum_point_group.rotation.v
        ) / 2.0
        position_reference.rotation.w = (
            position_reference.rotation.w + position_optimum_point_group.rotation.w
        ) / 2.0

    def _get_time_str(self) -> str:
        """Return the current time with the appropriate format."""
        return utils.astropy_time_from_tai_unix(utils.current_tai()).strftime(
            "%m/%d/%Y %H:%M:%S"
        )

    def _get_measurement_id(self) -> str:
        """Return the measument id.

        Returns
        -------
        `str`
            Measument id.
        """
        # I am not sure what the last number means.
        return (
            f"{self._telescope_position.azimuth:.2f}_"
            f"{self._telescope_position.elevation:.2f}_"
            f"{self._telescope_position.rotator:.2f}1"
        )

    async def _write_reply(self, reply: str) -> None:
        """Write a reply.

        Parameters
        ----------
        reply : `str`
            Reply string.
        """
        self.writer.write(reply.encode() + tcpip.TERMINATOR)
        await self.writer.drain()

    async def _warmup_laser(self) -> bool:
        """Simulate warming up the laser."""
        if self.is_ready():
            self.log.info("Laser already warm.")
        else:
            self.log.debug(f"Warming laser up. Will take: {self.laser_warmup_time}s")
            self._laser_warmup_start_tai = utils.current_tai()
            await asyncio.sleep(self.laser_warmup_time)
            self.log.debug("Laser warm up completed.")
            self._laser_warmup_start_tai = None
            self.laser_status = "LON"
        return True

    async def _handle_comand(self, command: str) -> None:
        """Handle a command from the client.

        Parameters
        ----------
        command : `str`
            Command.
        """
        command_handler, command_kwargs = self._parse_command(command)

        await command_handler(**command_kwargs)

    def _parse_command(self, command: str) -> tuple[typing.Any, dict[str, str]]:
        """Parse a command from the client.

        Parameters
        ----------
        command : `str`
            Command.

        Returns
        -------
        command_handler : `object`
            An awaitable method that handles the command.
        command_kwargs : `dict`[`str`, `str`]
            Dictionary with keywords arguments to pass to ``command_handler``.
        """
        command_name, _, args_str = (
            command.partition(" ")
            if command.startswith("?POS")
            else command.partition(":")
        )
        command_handler, args_regex = self.dispatchers.get(command_name, (None, None))

        if args_regex is not None:
            command_args_match = args_regex.match(args_str)
            command_kwargs = (
                command_args_match.groupdict()
                if command_args_match is not None
                else dict()
            )
        else:
            canned_reply = self.canned_replies.get(command)
            if canned_reply is not None:
                command_handler = self.write_good_reply
                command_kwargs = dict(reply=canned_reply)
            else:
                err_msg = f"Unsupported command {command!r}"
                self.log.error(err_msg)
                command_handler = self.write_error_reply
                command_kwargs = dict(reply=err_msg)

        return (command_handler, command_kwargs)
