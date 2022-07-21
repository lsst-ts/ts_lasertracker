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

import asyncio
import logging
import unittest

from lsst.ts import MTAlignment


class ModelTestCase(unittest.IsolatedAsyncioTestCase):
    """
    tests the Mock T2SA class. This is a simple stand-in for
    the T2SA application that we can connect to, and which has
    canned responses to some simple alignment system commands.
    """

    @classmethod
    def setUpClass(cls):
        cls.log = logging.getLogger()
        cls.log.addHandler(logging.StreamHandler())
        cls.log.setLevel(logging.INFO)

    async def asyncSetUp(self):
        self.mock_t2sa = MTAlignment.MockT2SA(port=0, log=self.log)
        await asyncio.wait_for(self.mock_t2sa.start_task, 5)

    async def asyncTearDown(self):
        if self.mock_t2sa:
            await asyncio.wait_for(self.mock_t2sa.close(), 5)

    async def test_connect(self):
        """
        Tests we can connect to the mock T2SA server
        """
        self.model = MTAlignment.AlignmentModel(
            host="127.0.0.1", port=self.mock_t2sa.port
        )
        await self.model.connect()
        assert self.model.connected
        await self.model.disconnect()
        assert not self.model.connected

    async def test_laser_status(self):
        """
        Tests mock T2SA reports laser status as "on"
        """
        self.model = MTAlignment.AlignmentModel(
            host="127.0.0.1", port=self.mock_t2sa.port
        )
        await self.model.connect()
        response = await self.model.send_command("?LSTA")
        assert response == "LON"
        await self.model.disconnect()

    async def test_emp(self):
        """
        Tests that we can execute a measurement plan, and that status
        queries while the tracker is measuring return "EMP"
        """
        self.model = MTAlignment.AlignmentModel(
            host="127.0.0.1", port=self.mock_t2sa.port
        )
        await self.model.connect()
        self.log.debug("sending measurement commmand")
        response = await self.model.send_command("!CMDEXE:M1M3")
        assert response == "ACK300"
        assert self.mock_t2sa.measuring
        self.log.debug("sending status check where we expect to receive EMP")
        response2 = await self.model.check_status()
        assert response2.strip() == "EMP"
        await asyncio.sleep(self.mock_t2sa.measurement_duration + 0.2)
        self.log.debug("sending status check where we expect to receive READY")
        response3 = await self.model.check_status()
        assert response3.strip() == "READY"
        await self.model.disconnect()
