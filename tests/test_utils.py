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

import numpy as np
import pytest
from lsst.ts.lasertracker import utils


def test_parse_single_point_measure() -> None:

    for x, y, z in np.round(np.random.rand(3, 3), 6):
        single_point_measure_sample = (
            "Measured single pt M1M3_1 result: "
            f"X:{x};Y:{y};Z:{z};08/19/2022 14:45:43 True"
        )

        data = utils.parse_single_point_measurement(single_point_measure_sample)

        assert data is not None
        assert data.x == x
        assert data.y == y
        assert data.z == z


def test_parse_single_point_measure_bad_data() -> None:

    single_point_measure_sample = "Bad data"

    with pytest.raises(RuntimeError):
        utils.parse_single_point_measurement(single_point_measure_sample)


def test_parse_offsets() -> None:

    for x, y, z, u, v, w in np.round(np.random.rand(3, 6), 6):

        offset_measure_sample = (
            "RefFrame:FrameM2_90.00_0.00_0.00_1;"
            f"X:{x};Y:{y};Z:{z};"
            f"Rx:{u};Ry:{v};Rz:{w};"
            "08/04/2022 16:27:48"
        )

        data = utils.parse_offsets(offset_measure_sample)
        assert data is not None
        assert data["target"] == "FrameM2_90.00_0.00_0.00_1"
        assert data["dX"] == x
        assert data["dY"] == y
        assert data["dZ"] == z
        assert data["dRX"] == u
        assert data["dRY"] == v
        assert data["dRZ"] == w
