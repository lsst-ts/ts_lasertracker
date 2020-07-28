import asynctest
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

    async def test_connect(self):
        """
        Tests we can connect to the mock T2SA server
        """
        self.model = alignmentModel.AlignmentModel("127.0.0.1", 50000)
        await self.model.connect()
        assert self.model.connected

    async def test_laser_status(self):
        """
        Tests mock T2SA reports laser status as "on"
        """
        self.model = alignmentModel.AlignmentModel("127.0.0.1", 50000)
        await self.model.connect()
        response = await self.model.send_msg("?LSTA")
        assert response == "LON\r\n"

    async def test_emp(self):
        """
        Tests mock T2SA reports laser status as "on"
        """
        self.model = alignmentModel.AlignmentModel("127.0.0.1", 50000)
        await self.model.connect()
        response = await self.model.send_msg("!CMDEXE:M1M3")
        assert response == "ACK300\r\n"  # mock acknkowleges command
        response2 = await self.model.check_status()
        assert response2 == "EMP\r\n" #  we should get an EMP response
        asyncio.sleep(3)
        response3 = await self.model.check_status()
        assert response3 == "READY\r\n" #  after waiting for measurement to execute, we should now get a READY response.

    async def tearDown(self):
        if self.mock_t2sa:
            await asyncio.wait_for(self.mock_t2sa.stop(), 5)
