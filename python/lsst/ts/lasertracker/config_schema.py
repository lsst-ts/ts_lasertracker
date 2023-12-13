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

__all__ = ["CONFIG_SCHEMA"]

import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_lasertracker/blob/master/schema/alignment.yaml
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: LaserTracker v1
description: Schema for LaserTracker CSC configuration files
type: object
properties:
  instances:
    type: array
    description: Configuration for each ESS instance.
    minItem: 1
    items:
      type: object
      properties:
        sal_index:
          type: integer
          description: SAL index of ESS instance.
          minimum: 1
        t2sa_host:
          description: TCP/IP host address of T2SA.
          type: string
        t2sa_port:
          description: TCP/IP port of T2SA.
          type: number
        read_timeout:
          description: Timeout for reading T2SA replies to commands (seconds).
          type: number
        targets:
          description: Names of valid targets. Must include "CAM", "M1M3", "M2", "TMA_CENTRAL" and "TMA_UPPER".
          type: array
          items:
            type: string
          minItems: 5
        num_iterations:
          description: Number of times to repeat measurements of a point group.
          type: number
        num_samples:
          description: Number of times to sample each point within a single visit.
          type: number
        randomize_points:
          description: Visit the SMRs in a random order?
          type: boolean
        station_lock:
          description: >-
            If true, prevents SpatialAnalyzer from automatically jumping stations
            if it detects that the tracker has drifted.
          type: boolean
        rms_tolerance:
          description: RMS least squares tolerance in mm.
          type: number
        max_tolerance:
          description: Maximum absolute tolerance  in mm.
          type: number
        two_face_az_tolerance:
          description: >-
            Maximum allowed azimuth divergence (degrees) when measuring
            the same point using the tracker's two different "facings".
          type: number
        two_face_el_tolerance:
          description: >-
            Maximum allowed elevation divergence (degrees) when measuring
            the same point using the tracker's two different "facings".
          type: number
        two_face_range_tolerance:
          description: >-
            Maximum allowed range divergence (mm) when measuring
            the same point using the tracker's two different "facings".
          type: number
        rms_drift_tolerance:
          description: RMS least squares tolerance (mm).
          type: number
        max_drift_tolerance:
          description: maximum absolute tolerance (mm).
          type: number
        power_lock:
          description: Enable the tracker’s camera? Used to help search for SMRs.
          type: boolean
        single_point_measurement_profile:
          description: Name of Spatial Analyzer measurement profile.
          type: string
      required:
        - sal_index
        - t2sa_host
        - t2sa_port
        - read_timeout
        - targets
        - num_iterations
        - num_samples
        - randomize_points
        - station_lock
        - rms_tolerance
        - max_tolerance
        - two_face_az_tolerance
        - two_face_el_tolerance
        - two_face_range_tolerance
        - rms_drift_tolerance
        - max_drift_tolerance
        - power_lock
        - single_point_measurement_profile
      additionalProperties: false
required:
  - instances
additionalProperties: false
"""
)
