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
import unittest

from lsst.ts import lasertracker
from lsst.ts.tcpip import LOCAL_HOST

STANDARD_TIMEOUT = 5


class ModelTestCase(unittest.IsolatedAsyncioTestCase):
    log: logging.Logger

    @classmethod
    def setUpClass(cls) -> None:
        cls.log = logging.getLogger(__name__)

    async def asyncSetUp(self) -> None:
        self.mock_t2sa = lasertracker.MockT2SA(port=0, log=self.log)
        # Set warmup time to 1.0 second to speed up testing.
        self.mock_t2sa.laser_warmup_time = 1.0
        await asyncio.wait_for(self.mock_t2sa.start_task, STANDARD_TIMEOUT)

    async def asyncTearDown(self) -> None:
        if self.mock_t2sa:
            await asyncio.wait_for(self.mock_t2sa.close(), STANDARD_TIMEOUT)

    async def test_connect(self) -> None:
        """Tests we can connect to the mock T2SA server."""
        self.model = lasertracker.T2SAModel(
            host=LOCAL_HOST,
            port=self.mock_t2sa.port,
            read_timeout=30,
            t2sa_simulation_mode=1,
            log=self.log,
        )
        await self.model.connect()
        assert self.model.connected
        await self.model.disconnect()
        assert not self.model.connected

    async def test_laser_status(self) -> None:
        """Tests mock T2SA reports laser status as "on"."""
        self.model = lasertracker.T2SAModel(
            host=LOCAL_HOST,
            port=self.mock_t2sa.port,
            read_timeout=30,
            t2sa_simulation_mode=1,
            log=self.log,
        )
        await self.model.connect()
        self.log.debug("Query initial laser status. should be LOFF")
        response = await self.model.send_command("?LSTA")
        assert response == "LOFF"

        self.log.debug("Power-up laser.")
        response = await self.model.send_command("!LST:1")

        self.log.debug("Query laser status while warming up, should be WARM.")
        response = await self.model.send_command("?LSTA")
        assert "WARM" in response

        self.log.debug("Waiting for laser to finish warming up.")
        await asyncio.wait_for(
            self.mock_t2sa.laser_warmup_task, timeout=STANDARD_TIMEOUT
        )

        self.log.debug("Query laser status, should be LON.")
        response = await self.model.send_command("?LSTA")
        assert response == "LON"

        await self.model.disconnect()
