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

import asyncio
import logging
import pathlib
import typing
import unittest

import numpy as np
import pytest
from lsst.ts import lasertracker, salobj
from lsst.ts.idl.enums.LaserTracker import SalIndex

STD_TIMEOUT = 15  # standard command timeout (sec)
TEST_CONFIG_DIR = pathlib.Path(__file__).parent.joinpath("data", "config")


class CscTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(
        self,
        index: SalIndex | int,
        config_dir: typing.Union[str, pathlib.Path, None],
        initial_state: typing.Union[salobj.State, int],
        override: str = "",
        simulation_mode: int = 2,
    ) -> lasertracker.LaserTrackerCsc:
        csc = lasertracker.LaserTrackerCsc(
            index=index,
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )
        return csc

    async def quick_power_on(self, laser_warmup_time: float, wait_warmup: bool) -> None:
        """Quickly power on laser.

        Parameters
        ----------
        laser_warmup_time : `float`
            How long should warmup time take (in seconds)?
        wait_warmup : `bool`
            Wait for warmup to finish?
        """
        # set warmup time to 0.
        assert self.csc._mock_t2sa is not None
        self.csc._mock_t2sa.laser_warmup_time = laser_warmup_time

        await self.remote.cmd_laserPower.set_start(power=1, timeout=STD_TIMEOUT)

        if wait_warmup:
            await self.csc._mock_t2sa.laser_warmup_task

    async def test_bin_script(self) -> None:
        await self.check_bin_script(
            name="LaserTracker",
            index=1,
            exe_name="run_lasertracker",
        )

    async def test_standard_state_transitions(self) -> None:
        async with self.make_csc(
            index=SalIndex.OTHER,
            config_dir=TEST_CONFIG_DIR,
            initial_state=salobj.State.STANDBY,
            override="",
            simulation_mode=2,
        ):
            await self.check_standard_state_transitions(
                override="",
                enabled_commands=[
                    "align",
                    "measureTarget",
                    "measurePoint",
                    "laserPower",
                    "healthCheck",
                    "powerOff",
                    "pointDelta",
                    "setReferenceGroup",
                    "halt",
                    "setWorkingFrame",
                    "loadSATemplateFile",
                    "measureDrift",
                    "resetT2SA",
                    "newStation",
                    "saveJobfile",
                ],
            )

    async def test_measure_target_laser_off(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            with pytest.raises(
                salobj.AckError,
                match="T2SA not ready: Laser status LOFF. Should be 'LON'",
            ):
                await self.remote.cmd_measureTarget.set_start(
                    target="M1M3", timeout=STD_TIMEOUT
                )

    async def test_measure_target_while_warming(self) -> None:
        async with self.make_csc(
            index=SalIndex.OTHER,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.quick_power_on(laser_warmup_time=10.0, wait_warmup=False)

            with pytest.raises(
                salobj.AckError,
                match="T2SA not ready: Laser status WARM. Should be 'LON'",
            ):
                await self.remote.cmd_measureTarget.set_start(
                    target="M1M3", timeout=STD_TIMEOUT
                )

            # Wait warmup to complete then try to measure again. This should
            # actually be an event from the CSC but we don't have it at this
            # point.
            await self.csc._mock_t2sa.laser_warmup_task

            self.remote.evt_positionPublish.flush()

            await self.remote.cmd_measureTarget.set_start(
                target="M1M3", timeout=STD_TIMEOUT
            )

            await self.assert_next_sample(
                self.remote.evt_positionPublish,
                flush=False,
                target="FrameM1M3_0.00_60.00_0.001",
                dX=pytest.approx(0.0, abs=1e-2),
                dY=pytest.approx(0.0, abs=1e-2),
                dZ=pytest.approx(0.0, abs=1e-2),
                dRX=pytest.approx(0.0, abs=6e-2),
                dRY=pytest.approx(0.0, abs=6e-2),
                dRZ=pytest.approx(0.0, abs=6e-2),
            )

    async def test_measure_target(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.quick_power_on(laser_warmup_time=0.0, wait_warmup=True)

            self.remote.evt_positionPublish.flush()

            await self.remote.cmd_measureTarget.set_start(
                target="M1M3", timeout=STD_TIMEOUT
            )

            await self.assert_next_sample(
                self.remote.evt_positionPublish,
                flush=False,
                target="FrameM1M3_0.00_60.00_0.001",
                dX=pytest.approx(0.0, abs=1e-2),
                dY=pytest.approx(0.0, abs=1e-2),
                dZ=pytest.approx(0.0, abs=1e-2),
                dRX=pytest.approx(0.0, abs=6e-2),
                dRY=pytest.approx(0.0, abs=6e-2),
                dRZ=pytest.approx(0.0, abs=6e-2),
            )

    async def test_health_check_fail_laser_off(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            # should fail because the laser is initially off.
            with pytest.raises(
                salobj.AckError,
                match="T2SA not ready: Laser status LOFF. Should be 'LON'",
            ):
                await self.remote.cmd_healthCheck.start(timeout=STD_TIMEOUT)

    async def test_health_check_laser_on(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.quick_power_on(laser_warmup_time=0.0, wait_warmup=True)
            with self.assertLogs(self.csc.log, level=logging.DEBUG) as csc_logs:
                await self.remote.cmd_healthCheck.start(timeout=STD_TIMEOUT)

            expected_logs = [
                log
                for sublist in [
                    (
                        f"DEBUG:LaserTracker:Running two face check for {target}.",
                        f"DEBUG:LaserTracker:Measuring drift for {target}.",
                    )
                    for target in ["CAM", "M1M3", "M2", "TMA_CENTRAL", "TMA_UPPER"]
                ]
                for log in sublist
            ]

            for log in expected_logs:
                assert log in csc_logs.output

    async def test_laser_power(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            # power on.
            await self.quick_power_on(laser_warmup_time=1.0, wait_warmup=False)

            # There's no event reporting the laser status. For now just check
            # that the mock controller was powered on.
            assert self.csc._mock_t2sa.laser_status == "WARM"

            # Again, since there is no event, wait for the warmup task to
            # complete.
            await self.csc._mock_t2sa.laser_warmup_task

            assert self.csc._mock_t2sa.laser_status == "LON"

            # power off
            await self.remote.cmd_laserPower.set_start(power=0, timeout=STD_TIMEOUT)

            assert self.csc._mock_t2sa.laser_status == "LOFF"
            assert self.csc._mock_t2sa.laser_warmup_task.done()

    async def test_measure_point_laser_off(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            with pytest.raises(
                salobj.AckError,
                match="T2SA not ready: Laser status LOFF. Should be 'LON'",
            ):
                await self.remote.cmd_measurePoint.set_start(
                    collection="A",
                    pointgroup="M1M3",
                    target="M1M3_1",
                    timeout=STD_TIMEOUT,
                )

    async def test_measure_point(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.quick_power_on(laser_warmup_time=0.0, wait_warmup=True)

            self.remote.evt_positionPublish.flush()

            await self.remote.cmd_measurePoint.set_start(
                collection="A",
                pointgroup="M1M3",
                target="M1M3_1",
                timeout=STD_TIMEOUT,
            )

            position = await self.assert_next_sample(
                self.remote.evt_positionPublish,
                flush=False,
                target="M1M3_1",
            )

            assert np.sqrt(
                position.dX**2.0 + position.dY**2.0 + position.dZ**2.0
            ) * 1e-3 == pytest.approx(8.4, rel=1e-3)

    async def test_point_delta(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.quick_power_on(laser_warmup_time=0.0, wait_warmup=True)

            await self.remote.cmd_pointDelta.set_start(
                collection_A="A",
                pointgroup_A="M2",
                target_A="M2_P2",
                collection_B="MEAS_M2_1",
                pointgroup_B="M2",
                target_B="M2_P2",
                timeout=STD_TIMEOUT,
            )

    async def test_set_reference_group(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.remote.cmd_setReferenceGroup.set_start(
                referenceGroup="M2",
                timeout=STD_TIMEOUT,
            )

            # Since there's no event yet with this information, check that it
            # gets updated in the mock controller.
            assert self.csc._mock_t2sa.reference_frame == "FRAMEM2"

    async def test_set_working_frame(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.remote.cmd_setWorkingFrame.set_start(
                workingFrame="",
                timeout=STD_TIMEOUT,
            )

            # TODO: Add some check.

    async def test_set_working_frame_invalid(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            with pytest.raises(salobj.AckError):
                await self.remote.cmd_setWorkingFrame.set_start(
                    workingFrame="INVALID",
                    timeout=STD_TIMEOUT,
                )

            # TODO: Add some check.

    async def test_halt(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.quick_power_on(laser_warmup_time=0.0, wait_warmup=True)
            self.csc._mock_t2sa.measurement_duration = 30.0

            self.csc.timeout_std = 0.1

            measure_task = asyncio.create_task(
                self.remote.cmd_measureTarget.set_start(
                    target="M1M3", timeout=STD_TIMEOUT
                )
            )

            # Give it some time for the measure to start.
            await asyncio.sleep(0.5)

            # Halt measurement
            await self.remote.cmd_halt.set_start(
                timeout=STD_TIMEOUT,
            )

            # I am not really sure what should happen in this case. I need
            # to get more informatino from the controller to write this checks
            # I am going to assume the measument command should fail.
            with pytest.raises(
                salobj.AckError, match="Error executing measure plan for M1M3"
            ):
                await measure_task

    async def test_load_sa_template_file(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            # We have to pass a file local to the SA service, running on
            # Windows.
            await self.remote.cmd_loadSATemplateFile.set_start(
                file=(
                    r"C:\\Program Files (x86)\\New River "
                    r"Kinematics\\T2SA\\T2SATemplateManual2022_07_19.xit64"
                ),
                timeout=STD_TIMEOUT,
            )

    async def test_load_sa_template_file_bad_path(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            # Use wrong extension
            with pytest.raises(
                salobj.AckError, match="SA Template file not found or loaded."
            ):
                await self.remote.cmd_loadSATemplateFile.set_start(
                    file=(
                        r"C:\\Program Files (x86)\\New River "
                        r"Kinematics\\T2SA\\T2SATemplateManual2022_07_19.txt"
                    ),
                    timeout=STD_TIMEOUT,
                )

    async def test_measure_drift_laser_off(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            with pytest.raises(
                salobj.AckError,
                match="T2SA not ready: Laser status LOFF. Should be 'LON'",
            ):
                await self.remote.cmd_measureDrift.set_start(
                    pointgroup="M2", timeout=STD_TIMEOUT
                )

    async def test_measure_drift(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.quick_power_on(laser_warmup_time=0.0, wait_warmup=True)

            await self.remote.cmd_measureDrift.set_start(
                pointgroup="M2",
                timeout=STD_TIMEOUT,
            )

            # TODO: Add some check.

    async def test_reset_t2sa(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.remote.cmd_resetT2SA.start(timeout=STD_TIMEOUT)

            # TODO: Add some checks

    async def test_new_station(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.remote.cmd_newStation.start(timeout=STD_TIMEOUT)

            # TODO: Add some checks

    async def test_save_job_file_invalid_path(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            with pytest.raises(salobj.AckError, match="Save SA job file failed."):
                await self.remote.cmd_saveJobfile.set_start(
                    file="/home/user/analyzer_data/test_job", timeout=STD_TIMEOUT
                )

    async def test_save_job_file(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.remote.cmd_saveJobfile.set_start(
                file=r"C:\Analyzer Data\TestJob", timeout=STD_TIMEOUT
            )

            # TODO: Add some checks

    async def test_align(self) -> None:
        async with self.make_csc(
            index=SalIndex.MTAlignment,
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.quick_power_on(laser_warmup_time=0.0, wait_warmup=True)

            for target in lasertracker.Target:
                await self.remote.cmd_align.set_start(
                    target=target,
                    timeout=STD_TIMEOUT,
                )

                offset = await self.assert_next_sample(
                    self.remote.evt_offsetsPublish,
                    target=f"Frame{target.name}_0.00_60.00_0.001",
                )

                if target == lasertracker.Target.M1M3:
                    # Alignment is with respect to m1m3 so these are 0.0
                    assert offset.dX == 0.0
                    assert offset.dY == 0.0
                    assert offset.dZ == 0.0
                    assert offset.dRX == 0.0
                    assert offset.dRY == 0.0
                    assert offset.dRZ == 0.0
                else:
                    assert abs(offset.dX) > 0.0
                    assert abs(offset.dY) > 0.0
                    assert abs(offset.dZ) > 0.0
                    assert abs(offset.dRX) > 0.0
                    assert abs(offset.dRY) > 0.0
                    assert abs(offset.dRZ) > 0.0
