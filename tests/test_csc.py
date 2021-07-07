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

    async def testBinScript(self):
        await self.check_bin_script("MTAlignment", 0, "run_MTAlignment.py")

    async def test_state_transitions(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=2,
        ):
            await self.check_standard_state_transitions(
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
                ]
            )


if __name__ == "__main__":
    unittest.main()
