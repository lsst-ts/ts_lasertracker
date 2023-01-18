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

__all__ = ["MockT2SAPointGroup"]

import numpy as np
from scipy.spatial.transform import Rotation

from ..utils import BodyRotation, CartesianCoordinate


class MockT2SAPointGroup:
    """Mock T2SA Point Group.

    A point group is a set of measuring points attached to a rigid body.

    This class contains the cartesian coordinates, rotation and radius of the
    body, plus definition of the location of the fiducials. With this
    information it is possible to compute the location of each individual point
    or the entire body in the cartesian coordinate system, plus the respective
    rotations of the body with respect to the cartesian axis.

    Parameters
    ----------
    origin : `CartesianCoordinate`
        The origin of the body.
    rotation : `BodyRotation`
        Rotation of the body with respect to the xyz axis.
    radius : float
        The radius of the body.

    Attributes
    ----------
    origin : `CartesianCoordinate`
        Position of the body origin in the cartesian coordinate system.
    rotation : `BodyRotation`
        Rotation of the body with respect to the xyz axis.
    radius : `float`
        Radius of the body (in meter).
    """

    def __init__(
        self,
        origin: CartesianCoordinate,
        rotation: BodyRotation,
        radius: float,
    ) -> None:
        self.origin = origin
        self.rotation = rotation
        self.radius = radius
        self._fiducial_angles = np.radians(np.array([0.0, 120.0, 240.0]))

    def get_fiducial_positions(
        self,
    ) -> list[CartesianCoordinate]:
        """Calculate the cartesian coordinate position of each individual
        measuring point that belongs to this point group.

        Returns
        -------
        `list` of `CartesianCoordinate`
            The cartesian coordinates of the fiducials in a group.
        """

        origin = self.origin.as_array()

        rotation = Rotation.from_rotvec(self.rotation.as_array()).as_matrix()

        return [
            np.dot(
                origin + self.radius * np.array([np.sin(angle), np.cos(angle), 0.0]),
                rotation,
            )
            for angle in self._fiducial_angles
        ]

    def get_one_fiducial_position(
        self,
        fiducial: int,
    ) -> CartesianCoordinate:
        """Calculate a single fiducial position.

        Parameters
        ----------
        fiducial : `int`
            Index of the point to get position (0 based index).

        Returns
        -------
        `CartesianCoordinate`
            The cartesian coordinates of the fiducial.
        """

        origin = self.origin.as_array()

        rotation = Rotation.from_rotvec(self.rotation.as_array()).as_matrix()

        angle = self._fiducial_angles[fiducial]

        return CartesianCoordinate(
            *np.dot(
                origin + self.radius * np.array([np.sin(angle), np.cos(angle), 0.0]),
                rotation,
            )
        )

    def get_number_of_fiducial(self) -> int:
        """Get the number of fiducials in this point group.

        Returns
        -------
        `int`
            Number of fiducials.
        """
        return len(self._fiducial_angles)
