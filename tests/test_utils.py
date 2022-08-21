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

from lsst.ts.MTAlignment import utils


def test_parse_single_point_measure() -> None:

    single_point_measure_sample = (
        "Measured single pt M1M3_1 result: "
        "X:-1.000000;Y:10.000000;Z:2.000000;08/19/2022 14:45:43 True"
    )

    data = utils.parse_single_point_measurement(single_point_measure_sample)

    assert data is not None
    assert data.x == -1.0
    assert data.y == 10.0
    assert data.z == 2.0


def test_parse_single_point_measure_bad_data() -> None:

    single_point_measure_sample = "Bad data"

    data = utils.parse_single_point_measurement(single_point_measure_sample)

    assert data is None


def test_parse_offsets() -> None:

    offset_measure_sample = (
        "RefFrame:FrameM2_90.00_0.00_0.00_1;"
        "X:-0.011787;Y:-0.049377;Z:0.022289;"
        "Rx:-0.000986;Ry:0.000586;Rz:0.000353;"
        "08/04/2022 16:27:48"
    )

    data = utils.parse_offsets(offset_measure_sample)
    assert data is not None
    assert data["target"] == "FrameM2_90.00_0.00_0.00_1"
    assert data["dX"] == -0.011787
    assert data["dY"] == -0.049377
    assert data["dZ"] == 0.022289
    assert data["dRX"] == -0.000986
    assert data["dRY"] == 0.000586
    assert data["dRZ"] == 0.000353
