import logging
import pathlib
import unittest
from lsst.ts import salobj
from lsst.ts import MTAlignment

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
            exe_name="run_MTAlignment",
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
