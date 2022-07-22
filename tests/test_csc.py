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

import logging
import pathlib
import unittest

from lsst.ts import MTAlignment, salobj

STD_TIMEOUT = 15  # standard command timeout (sec)
TEST_CONFIG_DIR = pathlib.Path(__file__).parent.joinpath("data", "config")


# Avoid adding more than one log handler;
# the handler (and level, if configured) persist between tests.
# Note: making this bool a class variable does not work; unittest restores
# the value for each test. A mutable object works, but is too much trouble.
add_stream_log_handler = True


class CscTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(self, config_dir, initial_state, override="", simulation_mode=2):
        global add_stream_log_handler
        csc = MTAlignment.AlignmentCSC(
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )
        if add_stream_log_handler:
            add_stream_log_handler = False
            csc.log.addHandler(logging.StreamHandler())
            csc.log.setLevel(logging.INFO)
        return csc

    async def test_bin_script(self):
        await self.check_bin_script(
            name="MTAlignment",
            index=0,
            exe_name="run_mtalignment",
        )

    async def test_standard_state_transitions(self):
        async with self.make_csc(
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

    async def test_basics(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            override="",
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.remote.cmd_measureTarget.set_start(
                target="M1M3", timeout=STD_TIMEOUT
            )
