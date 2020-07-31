import asynctest
import unittest
import logging
import asyncio
from lsst.ts.MTAlignment import mockT2sa
from lsst.ts.MTAlignment import alignmentModel


class AlignmentMockTestCases(asynctest.TestCase):
    """
    tests the Mock T2SA class. This is a simple stand-in for
    the T2SA application that we can connect to, and which has
    canned responses to some simple alignment system commands.
    """

    async def setUp(self):
        self.writer = None
        self.mock_t2sa = mockT2sa.MockT2SA()
        await asyncio.wait_for(self.mock_t2sa.start(), 5)
        self.log = logging.getLogger()
        self.log.addHandler(logging.StreamHandler())
        self.log.setLevel(logging.DEBUG)

    async def test_connect(self):
        """
        Tests we can connect to the mock T2SA server
        """
        self.model = alignmentModel.AlignmentModel("127.0.0.1", 50000)
        await self.model.connect()
        assert self.model.connected
        await self.model.disconnect()
        assert not self.model.connected

    async def test_laser_status(self):
        """
        Tests mock T2SA reports laser status as "on"
        """
        self.model = alignmentModel.AlignmentModel("127.0.0.1", 50000)
        await self.model.connect()
        response = await self.model.send_msg("?LSTA")
        assert response == "LON\r\n"
        await self.model.disconnect()

    async def test_emp(self):
        """
        Tests that we can execute a measurement plan, and that status
        queries while the tracker is measuring return "EMP"
        """
        self.model = alignmentModel.AlignmentModel("127.0.0.1", 50000)
        await self.model.connect()
        self.log.debug("sending measurement commmand")
        response = await self.model.send_msg("!CMDEXE:M1M3")
        assert response == "ACK300\r\n"
        self.assertTrue(self.mock_t2sa.measuring)
        self.log.debug("sending status check where we expect to receive EMP")
        response2 = await self.model.check_status()
        self.assertEqual(response2.strip(), "EMP")
        await asyncio.sleep(3)
        self.log.debug("sending status check where we expect to receive READY")
        response3 = await self.model.check_status()
        self.assertEqual(response3.strip(), "READY")
        await self.model.disconnect()

    async def test_measurement_query(self):
        """
        Tests that we can execute a measurement plan, and that status
        queries while the tracker is measuring return "EMP"
        """
        self.model = alignmentModel.AlignmentModel("127.0.0.1", 50000)
        await self.model.connect()
        response = await self.model.send_msg("?POS M1M3")
        self.assertEqual(response.strip(), "<m1m3_coordinates>")

        await self.model.disconnect()

    async def tearDown(self):
        if self.mock_t2sa:
            await asyncio.wait_for(self.mock_t2sa.stop(), 5)


if __name__ == "__main__":
    unittest.main()
