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

__all__ = [
    "BodyRotation",
    "CartesianCoordinate",
    "parse_offsets",
    "parse_single_point_measurement",
    "Target",
]

import enum
import re
from dataclasses import dataclass

import numpy as np

SINGLE_POINT_MEASURE_REGEX = re.compile(
    r"Measured single pt (.*) result: X:(?P<x>.*);Y:(?P<y>.*);Z:(?P<z>.*);(.*) (.*) (.*)"
)
OFFSET_MEASURE_REGEX = re.compile(
    r"RefFrame:(?P<target>.*);X:(?P<dX>.*);Y:(?P<dY>.*);Z:(?P<dZ>.*);"
    r"Rx:(?P<dRX>.*);Ry:(?P<dRY>.*);Rz:(?P<dRZ>.*);(.*) (.*)"
)


class Target(enum.IntEnum):
    """Target enum.

    This needs to be moved into ts_idl, or removed altogether. For now, we need
    this because the `align` command uses an enumeration for the target name,
    which we should probably convert to a string.
    """

    M2 = 1
    M1M3 = enum.auto()
    CAM = enum.auto()


@dataclass
class CartesianCoordinate:
    """Represents a cartesian coordinate."""

    x: float
    y: float
    z: float

    def as_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])


@dataclass
class BodyRotation:
    """Body rotation around each cartesian axis."""

    "Rotation about x, in deg"
    u: float
    "Rotation about y, in deg"
    v: float
    "Rotation about z, in deg"
    w: float

    def as_array(self) -> np.ndarray:
        return np.radians(np.array([self.u, self.v, self.w]))


def parse_single_point_measurement(
    measurement: str,
) -> None | CartesianCoordinate:
    """Parse single point measurement.

    Parameters
    ----------
    measurement : `str`
        Return value of single point measurement.

    Returns
    -------
    single_point_measurement : `CartesianCoordinate`
        Object with the x,y,z values obtained after parsing the input
        measurement.
    """
    measure_match = SINGLE_POINT_MEASURE_REGEX.match(measurement)
    single_point_measurement = (
        CartesianCoordinate(
            **dict([(k, float(v)) for k, v in measure_match.groupdict().items()])
        )
        if measure_match is not None
        else None
    )

    if single_point_measurement is None:
        raise RuntimeError(f"Failed to parse measurement: {measurement}")

    return single_point_measurement


def parse_offsets(
    measurement: str,
) -> dict[str, str | float] | None:
    """Takes a string containing spatial coordinates  from T2SA, and
    returns a dict with the following keys: RefFrame, X, Y, Z, Rx, Ry, Rz,
    and Timestamp.

    Parameters
    ----------
    measurement : `str`
        The ascii string from T2SA. We expect an ascii string delimited
        with colons and semicolons, formatted like this:

        <s>;X:<n>;Y:<n>;Z:<n>;Rx:<n>;Ry:<n>;Rz:<n>;<date>

        where <s> is the name of the reference frame and <n> is a
        floating point value.

    Returns
    -------
    offset : `dict` [`str`, `str` | `float`]
        Offsets obtained after parsing the input string.
    """

    measure_match = OFFSET_MEASURE_REGEX.match(measurement)
    offset = (
        dict(
            [
                (key, float(value) if key != "target" else value)
                for key, value in measure_match.groupdict().items()
            ]
        )
        if measure_match is not None
        else None
    )

    if offset is None:
        raise RuntimeError(f"Failed to parse measurement: {measurement}")

    return offset
