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

__all__ = ["MockT2SA"]

import asyncio
import logging
import re
import typing

from lsst.ts import tcpip
from lsst.ts import utils
from lsst.ts import salobj
from .mock_t2sa_target import MockT2SATarget
from ..utils import CartesianCoordinate, BodyRotation

# Good reply bodies. They should come after the initial "ACK-300 " in replies,
# and thus are intended as arguments to `write_good_reply`.
ALREADY_MEASURING_REPLY = "ACK000"
OK_REPLY = "ACK300"  # Command was accepted


class MockT2SA(tcpip.OneClientServer):
    """Emulate a New River Kinematics T2SA application.

    This is a very simplistic mock with canned replys
    for many commands.

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
    domain : `salobj.Domain`, optional
        Use this domain to subscribe to components telemetry and simulate
        feedback.

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
        domain: typing.Union[None, salobj.Domain] = None,
    ) -> None:
        self.measure_task = utils.make_done_future()
        self.reply_loop_task = utils.make_done_future()

        self._laser_warmup_task: typing.Union[None, asyncio.Task] = None
        self.laser_warmup_status: asyncio.Future = asyncio.Future()

        self.canned_replies = {
            "!SET_SIM:0": "ACK300",
            "!SET_SIM:1": "ACK300",
            "SET_RANDOMIZE_POINTS:0": "ACK300",
            "SET_RANDOMIZE_POINTS:1": "ACK300",
            "!RESET_T2SA": "ACK300",
            "!NEW_STATION": "ACK300",
        }
        self.command_handlers: dict[str, typing.Any] = {
            "!2FACE_CHECK": self.execute_two_face_check,
            "!CMDEXE": self.execute_measure_plan,
            "!HALT": self.halt,
            "!LOAD_SA_TEMPLATE_FILE": self.load_sa_template_file,
            "!LST": self.set_power,
            "!MEAS_DRIFT": self.execute_drift,
            "!MEAS_SINGLE_POINT": self.measure_single_point,
            "!PUBLISH_ALT_AZ_ROT": self.set_alt_az_rot,
            "!SAVE_SA_JOBFILE": self.save_sa_jobfile,
            "!SET_REFERENCE_GROUP": self.set_reference_group,
            "!SET_WORKING_FRAME": self.set_working_frame,
            "?LSTA": self.get_laser_status,
            "?OFFSET": self.write_target_offset,
            "?POINT_DELTA": self.measure_point_delta,
            "?POS CAM": self.write_target_position_cam,
            "?POS M1M3": self.write_target_position_m1m3,
            "?POS M2": self.write_target_position_m2,
            "?STAT": self.write_status,
        }

        self.command_arg_parsers = {
            "!2FACE_CHECK": re.compile(r"(?P<target>.*)"),
            "!CMDEXE": re.compile(r"(?P<target>.*)"),
            "!LOAD_SA_TEMPLATE_FILE": re.compile(r"(?P<file_path>.*)"),
            "!LST": re.compile(r"(?P<value>.*)"),
            "!MEAS_DRIFT": re.compile(r"(?P<target>.*)"),
            "!MEAS_SINGLE_POINT": re.compile(
                r"(?P<collection>.*);(?P<point_group>.*);(?P<target_n>.*)"
            ),
            "!PUBLISH_ALT_AZ_ROT": re.compile(r"(?P<alt>.*);(?P<az>.*);(?P<rot>.*)"),
            "!SAVE_SA_JOBFILE": re.compile(r"(?P<filename>.*)"),
            "!SET_REFERENCE_GROUP": re.compile(r"(?P<reference_group>.*)"),
            "!SET_WORKING_FRAME": re.compile(r"(?P<working_frame>.*)"),
            "?OFFSET": re.compile(r"(?P<reference_group>.*);(?P<target>.*)"),
            "?POINT_DELTA": re.compile(
                r"(?P<p1collection>.*);(?P<p1group>.*);(?P<p1>.*);"
                r"(?P<p2collection>.*);(?P<p2group>.*);(?P<p2>.*)"
            ),
        }

        self.collection_point_regexp = re.compile(r"(?P<group>.*)_P(?P<index>.*)")

        duplicate_keys = self.command_handlers.keys() & self.canned_replies.keys()
        if duplicate_keys:
            raise RuntimeError(
                f"Bug: keys {duplicate_keys} appear in both "
                "canned_replies and comamnd_handlers"
            )

        self._laser_warmup_start: typing.Union[None, float] = None
        self._reference_group = "M1M3"
        # TODO: Get valid working frame values.
        self.valid_working_frame = {""}
        # TODO: Get good default working frame value.
        self.working_frame = ""
        self.laser_status = "LOFF"
        self.laser_warmup_time = 60.0

        self.t2sa_status = "READY"

        # How long to wait while pretending to measure (seconds)
        self.measurement_duration = 2.0

        # Define the "bodies" in the system. Assume m1m3 is at the origin of
        # the coordinate frame pointing up, m2 is 3 meters away, pointing down
        # and camera is 2 meters away pointing down.
        self.position_optimum = dict(
            m1m3=MockT2SATarget(
                origin=CartesianCoordinate(0.0, 0.0, 0.0),
                rotation=BodyRotation(0.0, 0.0, 0.0),
                radius=8.40,
            ),
            m2=MockT2SATarget(
                origin=CartesianCoordinate(0.0, 0.0, 3.0),
                rotation=BodyRotation(0.0, 0.0, 0.0),
                radius=1.74,
            ),
            cam=MockT2SATarget(
                origin=CartesianCoordinate(0.0, 0.0, 2.0),
                rotation=BodyRotation(0.0, 0.0, 0.0),
                radius=0.85,
            ),
        )

        self.position_current = dict(
            m1m3=MockT2SATarget(
                origin=CartesianCoordinate(0.0, 0.0, 0.0),
                rotation=BodyRotation(0.0, 0.0, 0.0),
                radius=8.40,
            ),
            m2=MockT2SATarget(
                origin=CartesianCoordinate(0.0, 0.0, 3.0),
                rotation=BodyRotation(0.0, 0.0, 0.0),
                radius=1.74,
            ),
            cam=MockT2SATarget(
                origin=CartesianCoordinate(0.0, 0.0, 2.0),
                rotation=BodyRotation(0.0, 0.0, 0.0),
                radius=0.85,
            ),
        )

        # Subscribe to data from m1m3, m2 hexapod and cam hexapod to use them
        # on the position of the elements. This allows us to interact with the
        # components in simulation mode and emulate an alignment sequence.
        self.remotes = (
            dict(
                m1m3=salobj.Remote(
                    domain=domain,
                    name="MTM1M3",
                    readonly=True,
                    include=["hardpointActuatorData"],
                ),
                cam=salobj.Remote(
                    domain=domain,
                    name="MTHexapod",
                    index=1,
                    readonly=True,
                    include=["application"],
                ),
                m2=salobj.Remote(
                    domain=domain,
                    name="MTHexapod",
                    index=2,
                    readonly=True,
                    include=["application"],
                ),
            )
            if domain is not None
            else dict()
        )

        self._tel_az = 90.0
        self._tel_alt = 0.0
        self._tel_rot = 0.0

        super().__init__(
            name="MockT2SA",
            host=host,
            port=port,
            connect_callback=self.run_reply_loop,
            log=log,
        )

    @property
    def reference_frame(self) -> str:
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
        return self.laser_status == "LON" and self.laser_warmup_status.done()

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
            return "READY"

    async def execute_drift(self, target: str) -> None:
        """Pretend to execute two face check.

        Parameters
        ----------
        target : `str`
            Target to execute drift measurements (e.g. M1M3, M2, CAM).
        """
        await self._execute_action("DRIFT", target)

    async def execute_two_face_check(self, target: str) -> None:
        """Pretend to execute two face check.

        Parameters
        ----------
        target : `str`
            Target to execute 2 face check (e.g. M1M3, M2, CAM).
        """
        await self._execute_action("2FACE", target)

    async def execute_measure_plan(self, target: str) -> None:
        """Pretend to execute a measurment plan.

        Acknowledge the request to measure, then pretend to measure.

        Parameters
        ----------
        target : `str`
            Target to measure (e.g. M1M3, M2, CAM).
        """
        await self._execute_action("EMP", target)

    async def halt(self) -> None:
        """Halt any ongoing measurement."""
        if not self.measure_task.done():
            self.measure_task.cancel()
            try:
                await self.measure_task
            except asyncio.CancelledError:
                pass
            except Exception:
                self.log.exception("Error canceling measure task.")

        self.t2sa_status = "READY"
        await self.write_good_reply("READY")

    async def load_sa_template_file(self, file_path: str) -> None:
        """Pretend to load an SA Template File.

        Parameters
        ----------
        file_path : `str`
            Path of the file in the SA node.
        """

        sa_template_dir = r"C:\\Program Files (x86)\\New River Kinematics\\T2SA\\"

        if file_path.startswith(sa_template_dir) and file_path.endswith(".xit64"):
            await self.write_good_reply("READY")
        else:
            await self.write_error_reply("SA Template file not found or loaded.")

    async def _execute_action(self, action: str, target: str) -> None:
        """Pretend to execute a certain action.

        Parameters
        ----------
        action : `str`
            Name of the action.
        target : `str`
            Target the action is being executed for.
        """
        self.log.debug(f"Executing {action} for {target}.")

        # Schedule task that will emulate measurement in the background
        if self.is_measuring():
            await self.write_good_reply(ALREADY_MEASURING_REPLY)
        elif not self.is_ready():
            await self.write_error_reply(
                f"T2SA not ready: {self.get_readiness_status()}."
            )
        elif target.lower() not in self.position_optimum:
            await self.write_error_reply(f"No target {target}.")
        else:
            self.t2sa_status = action
            self.measure_task = asyncio.create_task(self.measure())
            await self.write_good_reply(OK_REPLY)

    async def write_status(self) -> None:
        """Reply with current status.

        While pretend measuring is happening, status should return
        "EMP" -- Executing Measurement Plan
        """

        await self.write_good_reply(self.t2sa_status)

        # if self.is_measuring():
        #     await self.write_good_reply("EMP")
        # else:
        #     await self.write_good_reply("READY")

    async def write_target_position_m1m3(self) -> None:
        """Write the target position for m1m3."""
        await self.write_target_position("m1m3")

    async def write_target_position_m2(self) -> None:
        """Write the target position for m2."""
        await self.write_target_position("m2")

    async def write_target_position_cam(self) -> None:
        """Write the target position for camera."""
        await self.write_target_position("cam")

    async def write_target_position(self, target_name: str) -> None:
        """Reply with the input target position.

        Parameters
        ----------
        arg_str : `str`
            The input argument passed to the execution, must contain the target
            name.
        """

        if self.is_measuring():
            await self.write_error_reply("Ongoing measurements.")
        elif self.measure_task.cancelled():
            await self.write_error_reply("Measurement failed.")
        else:
            body_name = target_name.lower()
            if body_name not in self.position_current:
                await self.write_error_reply(f"No target {body_name}.")
            else:
                await self._write_position(body_name=body_name)

    async def write_target_offset(self, reference_group: str, target: str) -> None:
        """Reply with target offset based on input parameters.

        Parameters
        ----------
        reference_group : `str`
            Which "target" to use as a reference (e.g. M1M3, M2, CAM).
        target : `str`
            Which target to get offset for (e.g. M1M3, M2, CAM).
        """

        if reference_group.lower() not in self.position_optimum:
            await self.write_error_reply(f"No {reference_group} reference group.")
        elif target.lower() not in self.position_current:
            await self.write_error_reply(f"No target {target}.")
        else:
            await self._write_offset(
                reference_group=reference_group.lower(), target=target.lower()
            )

    async def measure_point_delta(
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
            Name of pointgroup the point 1 is in
        p1group : `str`
            Name of point 1
        p1 : `str`
            name of collection point 1 is in.
        p2collection : `str`
            Name of pointgroup the point 2 is in
        p2group : `str`
            Name of point 2
        p2 : `str`
            name of collection point 2 is in.
        """
        # Note: I am not really sure what this method does. It seems like it
        # reads previously made measurements and compute the offset between
        # them. I am simply going to emulate that without trying to keep track
        # about collections and pre-existing measurements.

        if p1group.lower() not in self.position_current:
            await self.write_error_reply(f"No group {p1group}")
            return

        if p2group.lower() not in self.position_current:
            await self.write_error_reply(f"No group {p2group}")
            return

        p1_index, error_message = self.parse_collection_point(
            point_name=p1, group=p1group
        )

        if error_message:
            await self.write_error_reply(error_message)
            return

        p2_index, error_message = self.parse_collection_point(
            point_name=p2, group=p2group
        )

        if error_message:
            await self.write_error_reply(error_message)
            return

        p1_position = self.position_current[p1group.lower()].get_target_position(
            p1_index
        )
        p2_position = self.position_current[p2group.lower()].get_target_position(
            p2_index
        )

        await self.write_good_reply(
            f"Measured single pt {p2} result: "
            f"X:{p2_position.x-p1_position.x};"
            f"Y:{p2_position.y-p1_position.y};"
            f"Z:{p2_position.z-p1_position.z};"
            f"{self._get_time_str()} False"
        )

    def parse_collection_point(
        self, point_name: str, group: str
    ) -> typing.Tuple[int, str]:
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
                <= self.position_current[group.lower()].get_number_of_targets()
            )
            return index - 1, ""
        except Exception as e:
            return 0, (
                f"Unable to parse p1={point_name}. Must be in the format {group}_N, "
                f"where N goes from 1 to {self.position_current[group.lower()].get_number_of_targets()}. "
                f"Exception: {e}."
            )

    async def get_laser_status(self) -> None:
        """Write laser status."""
        if self.laser_status == "WARM":
            assert self._laser_warmup_start is not None
            remaining_warmup_time = utils.current_tai() - self._laser_warmup_start
            await self.write_good_reply(f"WARM, {remaining_warmup_time:.2f} seconds")
        else:
            await self.write_good_reply(self.laser_status)

    async def measure_single_point(
        self, collection: str, point_group: str, target_n: str
    ) -> None:
        """Measure a single point.

        Parameters
        ----------
        collection : `str`
            An identifier to group this measurement internally.
        point_group : `str`
            Which group to measure (e.g. M1M3, M2, CAM).
        target_n : `str`
            A string representation of which target from the group to measure.
            The format is <point_group>_<index>, where index is the 1-based
            index of the target in the group.
        """

        if not self.is_ready():
            await self.write_error_reply(
                f"T2SA not ready: {self.get_readiness_status()}."
            )
            return

        target_id = int(target_n.split("_")[-1]) - 1
        target_position = self.position_current[
            point_group.lower()
        ].get_target_position(target=target_id)

        await self.write_good_reply(
            f"Measured single pt {target_n} result: "
            f"X:{target_position.x*1e3:.6f};"
            f"Y:{target_position.y*1e3:.6f};"
            f"Z:{target_position.z*1e3:.6f};"
            f"{self._get_time_str()} True"
        )

    async def set_alt_az_rot(self, alt: str, az: str, rot: str) -> None:
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
            self._tel_alt = float(alt)
            self._tel_az = float(az)
            self._tel_rot = float(rot)
            await self.write_good_reply("READY")
        except ValueError:
            await self.write_error_reply(
                f"Failed to convert a value to float: {alt}/{az}/{rot}."
            )
        except Exception as e:
            await self.write_error_reply(f"Error: {e}")

    async def save_sa_jobfile(self, filename: str) -> None:
        """Pretend to save SA job file.

        Parameters
        ----------
        filename : `str`
            Name of the file must match a Windows path, e.g. C:.
        """

        if filename.startswith("C:"):
            await self.write_good_reply("READY")
        else:
            await self.write_error_reply("Save SA job file failed.")

    async def set_reference_group(self, reference_group: str) -> None:
        """Set nominal point group to locate station to and provide
        data relative to.

        Parameters
        ----------
        reference_group : `str`
            New reference group.
        """

        if reference_group.lower() not in self.position_optimum:
            await self.write_error_reply(
                f"No group {reference_group}. Must be one of {self.position_optimum.keys()}."
            )
        else:
            self._reference_group = reference_group
            await self.write_good_reply("READY")

    async def set_working_frame(self, working_frame: str) -> None:
        """Set the working frame.

        This is the frame whose coordinate system all coordinates will be
        provided relative to.

        Parameters
        ----------
        working_frame : str
            New value of the working frame.
        """

        if working_frame not in self.valid_working_frame:
            await self.write_error_reply("POS: NotFound")
        else:
            self.working_frame = working_frame
            await self.write_good_reply("READY")

    async def set_power(self, value: str) -> None:
        """Set power status.

        Parameters
        ----------
        power : `str`
            The input argument passed to the execution. If 0 power off, it 1
            power on and execute warmup procedure.
        """

        if value == "0":
            await self.power_off()
        elif value == "1":
            await self.power_on()
        else:
            await self.write_error_reply(f"Invalid input argument: {value}.")

    async def power_off(self) -> None:
        """Set power off."""
        self.laser_status = "LOFF"
        await self.write_good_reply("Tracker Interface Stopped: True")

    async def power_on(self) -> None:
        """Set power on."""
        self.laser_status = "WARM"
        self._laser_warmup_task = asyncio.create_task(self._warmup_laser())
        await self.write_good_reply("Tracker Interface Started: True")

    async def _write_position(self, body_name: str) -> None:
        """Write position.

        Parameters
        ----------
        body_name : `str`
            Name of the body to get position.
        """
        body = self.position_current[body_name]
        offset_coord, offset_rotation = (
            self.get_offset_from_telemetry(body_name)
            if body_name in self.remotes
            else self._get_zero_offset()
        )

        await self.write_good_reply(
            f"RefFrame:{self.reference_frame};"
            f"X:{body.origin.x+offset_coord.x};"
            f"Y:{body.origin.y+offset_coord.y};"
            f"Z:{body.origin.z+offset_coord.z};"
            f"Rx:{body.rotation.u+offset_rotation.u};"
            f"Ry:{body.rotation.v+offset_rotation.v};"
            f"Rz:{body.rotation.w+offset_rotation.w};"
            f"{self._get_time_str()}"
        )

    def get_offset_from_telemetry(
        self, body_name: str
    ) -> typing.Tuple[CartesianCoordinate, BodyRotation]:
        """Get offset from zero position based on telemetry for a body.

        Parameters
        ----------
        body_name : `str`
            Name of the body to get position.
        """
        return (
            self._get_m1m3_data()
            if body_name == "m1m3"
            else self._get_hexapod_data(body_name)
        )

    def _get_zero_offset(self) -> typing.Tuple[CartesianCoordinate, BodyRotation]:
        """Get coordinate and rotation offsets equal to zero.

        Returns
        -------
        typing.Tuple[CartesianCoordinate, BodyRotation]
            xyz and uvw offsets.
        """
        return (
            CartesianCoordinate(x=0.0, y=0.0, z=0.0),
            BodyRotation(u=0.0, v=0.0, w=0.0),
        )

    def _get_m1m3_data(self) -> typing.Tuple[CartesianCoordinate, BodyRotation]:
        """Get offset from telemetry for M1M3.

        Returns
        -------
        typing.Tuple[CartesianCoordinate, BodyRotation]
            xyz and uvw offsets.
        """
        m1m3_data = self.remotes["m1m3"].tel_hardpointActuatorData.get()
        return (
            (
                CartesianCoordinate(
                    x=m1m3_data.xPosition,
                    y=m1m3_data.yPosition,
                    z=m1m3_data.zPosition,
                ),
                BodyRotation(
                    u=m1m3_data.xRotation,
                    v=m1m3_data.yRotation,
                    w=m1m3_data.zRotation,
                ),
            )
            if m1m3_data is not None
            else self._get_zero_offset()
        )

    def _get_hexapod_data(
        self, body_name: str
    ) -> typing.Tuple[CartesianCoordinate, BodyRotation]:
        """Get offset from telemetry for the hexapods.

        Parameters
        ----------
        body_name : `str`
            Which hexapod, M2 or CAM?

        Returns
        -------
        typing.Tuple[CartesianCoordinate, BodyRotation]
            xyz and uvw offsets.
        """
        hexapod_data = self.remotes[body_name].tel_application.get()
        return (
            (
                CartesianCoordinate(
                    x=hexapod_data.position[0] * 1e-6,
                    y=hexapod_data.position[1] * 1e-6,
                    z=hexapod_data.position[2] * 1e-6,
                ),
                BodyRotation(
                    u=hexapod_data.position[3],
                    v=hexapod_data.position[4],
                    w=hexapod_data.position[5],
                ),
            )
            if hexapod_data is not None
            else self._get_zero_offset()
        )

    def run_reply_loop(self, server: tcpip.OneClientServer) -> None:
        """Method to respond to a connection request.

        This is passed in to the `tcpip.OneClientServer` as a callback method.

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

        await asyncio.gather(*[remote.start_task for remote in self.remotes.values()])

        self.log.debug("reply loop begins")
        try:
            while self.connected:
                recv_bytes = await self.reader.readline()
                self.log.debug(f"Mock T2SA received cmd: {recv_bytes}")
                if not recv_bytes:
                    self.log.info(
                        "read loop ending; null data read indicates client hung up"
                    )
                    break

                recv_message = recv_bytes.decode().strip()
                if not recv_message:
                    continue

                await self._handle_message(recv_message)
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
        self.t2sa_status = "READY"
        self.log.debug("stop pretending to measure")

    async def write_good_reply(self, reply: str) -> None:
        """Write a good reply to the client, prefixed with 'ACK-300 '

        Parameters
        ----------
        reply : `str`
            The reply (without a leading ACK-300 or trailing "\r\n")
        """
        await self._write_reply(f"ACK-300 {reply}")

    async def write_error_reply(self, reply: str) -> None:
        """Write an error reply to the client, prefixed with 'ERR-300 '

        Parameters
        ----------
        reply : `str`
            The reply (without a leading ERR-300 or trailing "\r\n")
        """
        await self._write_reply(f"ERR-300 {reply}")

    async def _write_offset(self, reference_group: str, target: str) -> None:
        """Write offset.

        Parameters
        ----------
        reference_group : `str`
            Reference group for the offset.
        target : `str`
            Target to comput offset for.
        """

        position_optimum_reference = self.position_optimum[reference_group]
        position_optimum_target = self.position_optimum[target]

        origin_x = (
            position_optimum_target.origin.x - position_optimum_reference.origin.x
        )
        origin_y = (
            position_optimum_target.origin.y - position_optimum_reference.origin.y
        )
        origin_z = (
            position_optimum_target.origin.z - position_optimum_reference.origin.z
        )
        origin_u = (
            position_optimum_target.rotation.u - position_optimum_reference.rotation.u
        )
        origin_v = (
            position_optimum_target.rotation.v - position_optimum_reference.rotation.v
        )
        origin_w = (
            position_optimum_target.rotation.w - position_optimum_reference.rotation.w
        )

        position_reference = self.position_current[reference_group]
        position_target = self.position_current[target]

        offset_coord, offset_rotation = (
            self.get_offset_from_telemetry(target)
            if target in self.remotes
            else self._get_zero_offset()
        )

        dx = position_target.origin.x - position_reference.origin.x + offset_coord.x
        dy = position_target.origin.y - position_reference.origin.y + offset_coord.y
        dz = position_target.origin.z - position_reference.origin.z + offset_coord.z
        du = (
            position_target.rotation.u
            - position_reference.rotation.u
            + offset_rotation.u
        )
        dv = (
            position_target.rotation.v
            - position_reference.rotation.v
            + offset_rotation.v
        )
        dw = (
            position_target.rotation.w
            - position_reference.rotation.w
            + offset_rotation.w
        )

        await self.write_good_reply(
            f"RefFrame:Frame{target.upper()}_{self._get_measurement_id()};"
            f"X:{dx-origin_x};"
            f"Y:{dy-origin_y};"
            f"Z:{dz-origin_z};"
            f"Rx:{du-origin_u};"
            f"Ry:{dv-origin_v};"
            f"Rz:{dw-origin_w};"
            f"{self._get_time_str()}"
        )

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
        return f"{self._tel_az:.2f}_{self._tel_alt:.2f}_{self._tel_rot:.2f}_1"

    async def _write_reply(self, reply: str) -> None:
        """Write reply.

        Parameters
        ----------
        reply : `str`
            Reply string.
        """
        self.writer.write(reply.encode() + tcpip.TERMINATOR)
        await self.writer.drain()

    async def _warmup_laser(self) -> None:
        """Simulate warming up the laser."""
        if self.laser_warmup_status.done():
            self.log.info("Laser already warm.")

        self.log.debug(f"Warming laser up. Will take: {self.laser_warmup_time}s")
        self._laser_warmup_start = utils.current_tai()
        await asyncio.sleep(self.laser_warmup_time)
        self.log.debug("Laser warm up completed.")
        self._laser_warmup_start = None
        self.laser_status = "LON"
        self.laser_warmup_status.set_result(True)

    async def _handle_message(self, message: str) -> None:
        """Handle message from client.

        Parameters
        ----------
        message : `str`
            Message from client to process.
        """

        command_name, command_kwargs = self._parse_message(message)

        self.log.debug(f"{command_name}::{command_kwargs}")

        if command_name in self.command_handlers:
            if command_name in self.command_arg_parsers and command_kwargs is None:
                await self.write_error_reply(
                    f"Expected arguments for {command_name} got None when processing message {message}."
                )
            else:
                await (
                    self.command_handlers[command_name](**command_kwargs)
                    if command_kwargs is not None
                    else self.command_handlers[command_name]()
                )

        else:
            canned_reply = self.canned_replies.get(message)
            if canned_reply:
                await self.write_good_reply(canned_reply)
            else:
                err_msg = f"Unsupported command {message!r}"
                self.log.error(err_msg)
                await self.write_error_reply(f"{err_msg}")

    def _parse_message(
        self, message: str
    ) -> typing.Tuple[typing.Union[str, None], typing.Union[dict[str, str], None]]:
        """Parse message from client.

        Parameters
        ----------
        message : `str`
            Received message from client.

        Returns
        -------
        `str` or `None`, `dict`[`str`, `str`] or `None`
            A tuple with command name and argument.
        """
        message_split = message.split(":", maxsplit=1)
        command_name = message_split[0]
        command_args = (
            self.command_arg_parsers[command_name].match(message_split[1])
            if len(message_split) > 1 and command_name in self.command_arg_parsers
            else None
        )

        return (
            command_name,
            command_args.groupdict() if command_args is not None else None,
        )
