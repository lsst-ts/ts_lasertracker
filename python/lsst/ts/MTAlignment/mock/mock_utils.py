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
    "OPTIMAL_POSITION",
    "get_random_initial_position",
]

from dataclasses import dataclass

import numpy as np

from ..utils import BodyRotation, CartesianCoordinate
from .mock_t2sa_point_group import MockT2SAPointGroup

# Define the "bodies" in the system. Assume m1m3 is at the origin of
# the coordinate frame pointing up, m2 is 3 meters away, pointing down
# and camera is 2 meters away pointing down.
OPTIMAL_POSITION = dict(
    m1m3=MockT2SAPointGroup(
        origin=CartesianCoordinate(0.0, 0.0, 0.0),
        rotation=BodyRotation(0.0, 0.0, 0.0),
        radius=8.40,
    ),
    m2=MockT2SAPointGroup(
        origin=CartesianCoordinate(0.0, 0.0, 3.0),
        rotation=BodyRotation(0.0, 0.0, 0.0),
        radius=1.74,
    ),
    cam=MockT2SAPointGroup(
        origin=CartesianCoordinate(0.0, 0.0, 2.0),
        rotation=BodyRotation(0.0, 0.0, 0.0),
        radius=0.85,
    ),
)


def get_random_initial_position() -> dict[str, MockT2SAPointGroup]:
    """Get random initial position.

    Randomize position by 1mm and rotation by (approx) 20 arcsec.

    Returns
    -------
    `dict` [`str`, `MockT2SAPointGroup`]
        _description_
    """
    return dict(
        m1m3=MockT2SAPointGroup(
            origin=CartesianCoordinate(*np.random.normal(0.0, 1e-3, 3)),
            rotation=BodyRotation(*np.random.normal(0.0, 6e-3, 3)),
            radius=8.40,
        ),
        m2=MockT2SAPointGroup(
            origin=CartesianCoordinate(
                *(np.array([0.0, 0.0, 3.0]) + np.random.normal(0.0, 1e-3, 3))
            ),
            rotation=BodyRotation(*np.random.normal(0.0, 6e-3, 3)),
            radius=1.74,
        ),
        cam=MockT2SAPointGroup(
            origin=CartesianCoordinate(
                *(np.array([0.0, 0.0, 2.0]) + np.random.normal(0.0, 1e-3, 3))
            ),
            rotation=BodyRotation(*np.random.normal(0.0, 6e-3, 3)),
            radius=0.85,
        ),
    )


@dataclass
class TelescopePosition:
    """Store telescope position.

    Attributes
    ----------
    azimuth : `float`
        Telescope azimuth, in deg.
    elevation : `float`
        Telescope elevation, in deg.
    rotator : `float`
        Rotator position, in deg.
    """

    azimuth = 90.0
    elevation = 0.0
    rotator = 0.0
