import pathlib
import unittest
from lsst.ts import salobj
from lsst.ts import MTAlignment


STD_TIMEOUT = 15  # standard command timeout (sec)
TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")


class CscTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(self, initial_state, config_dir, simulation_mode):

        return MTAlignment.AlignmentCSC(
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
        )

    async def tearDown(self):
        if self.csc.model is not None:
            await self.csc.model.disconnect()

    async def test_state_transitions_t2sa(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.check_standard_state_transitions(
                settingsToApply="t2sa_test.yaml",
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
            await self.tearDown()

    async def test_basics(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await salobj.set_summary_state(
                self.remote, salobj.State.ENABLED, settingsToApply="t2sa_test.yaml"
            )
            await self.remote.cmd_measureTarget.set_start(
                target="M1M3", timeout=STD_TIMEOUT
            )
            await self.tearDown()

    async def test_measure_m2(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await salobj.set_summary_state(
                self.remote, salobj.State.ENABLED, settingsToApply="t2sa_test.yaml"
            )
            await self.remote.cmd_measureTarget.set_start(
                target="M2", timeout=STD_TIMEOUT
            )
            assert self.csc.last_measurement is not None
            assert (
                self.csc.last_measurement["Rx"] != 0
            )  # It's probably not gonna be zero, right?
            await self.tearDown()

    async def test_measure_cam(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await salobj.set_summary_state(
                self.remote, salobj.State.ENABLED, settingsToApply="t2sa_test.yaml"
            )
            await self.remote.cmd_measureTarget.set_start(
                target="CAM", timeout=STD_TIMEOUT
            )
            assert self.csc.last_measurement is not None
            assert (
                self.csc.last_measurement["Rx"] != 0
            )  # It's probably not gonna be zero, right?
            await self.tearDown()

    async def test_measure_m1m3(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await salobj.set_summary_state(
                self.remote, salobj.State.ENABLED, settingsToApply="t2sa_test.yaml"
            )
            await self.remote.cmd_measureTarget.set_start(
                target="M1M3", timeout=STD_TIMEOUT
            )
            assert self.csc.last_measurement is not None
            assert (
                self.csc.last_measurement["Rx"] != 0
            )  # It's probably not gonna be zero, right?
            await self.tearDown()


if __name__ == "__main__":
    unittest.main()
