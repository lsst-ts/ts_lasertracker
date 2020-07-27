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

    async def setup(self):
        self.writer = None
        self.mock_t2sa = mockT2sa.MockT2SA()
        await asyncio.wait_for(self.mock_t2sa.start(), 5)
        rw_coro = asyncio.open_connection("127.0.0.1", port=50000)
        self.reader, self.writer = await asyncio.wait_for(rw_coro, timeout=5)

    async def test_connect(self):
        self.model = alignmentModel.AlignmentModel("127.0.0.1", 50000)
        await self.model.connect()
        assert self.model.connected

    async def teardown(self):
        if self.mock_t2sa:
            await asyncio.wait_for(self.mock_t2sa.stop(), 5)
