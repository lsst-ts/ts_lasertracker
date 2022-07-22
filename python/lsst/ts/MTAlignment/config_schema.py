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

__all__ = ["CONFIG_SCHEMA"]

import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_MTAlignment/blob/master/schema/alignment.yaml
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: Alignment v2
description: Schema for MT Alignment CSC configuration files
type: object
properties:
  t2sa_ip:
    description: IP address of T2SA instance.
    type: string
  t2sa_port:
    description: port of T2SA instance.
    type: number
  num_iterations:
    description: number of times to repeat measurements of a point group
    type: number
  num_samples:
    description: number of times to sample each point within a single visit
    type: number
  randomize_points:
    description: if true, visit the SMRs in a random order
    type: boolean
  station_lock:
    description: >-
      if true, prevents SpatialAnalyzer from automatically jumping stations
      if it detects that the tracker has drifted
    type: boolean
  rms_tolerance:
    description: RMS least squares tolerance in mm
    type: number
  max_tolerance:
    description: maximum absolute tolerance  in mm
    type: number
  two_face_az_tolerance:
    description: >-
      maximum azimuth divergence allowed when measuring the same point using the
      tracker's two different "facings" in decimal degrees
    type: number
  two_face_el_tolerance:
    description: >-
      maximum elevation divergence allowed when measuring the same point using the
      tracker's two different "facings" in decimal degrees
    type: number
  two_face_range_tolerance:
    description: >-
      maximum range divergence allowed when measuring the same point using the
      tracker's two different "facings" in millimeters
    type: number
  rms_drift_tolerance:
    description: RMS least squares tolerance in mm
    type: number
  max_drift_tolerance:
    description: maximum absolute tolerance  in mm
    type: number
  power_lock:
    description: if true, enables the tracker’s camera (used to help search for SMRs).
    type: boolean
  single_point_measurement_profile:
    description: name of Spatial Analyzer measurement profile
    type: string
requiredProperties:
  - t2sa_ip
  - t2sa_port
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
"""
)
