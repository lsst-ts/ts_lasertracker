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
title: LaserTracker v3
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
        zero_points:
          description: Zero points for components positions
          type: object
          properties:
            m2:
              description: Zero point for M2.
              type: object
              properties:
                x:
                  description: Zero point in x in mm.
                  type: number
                y:
                  description: Zero point in y in mm.
                  type: number
                z:
                  description: Zero point in z in mm.
                  type: number
                u:
                  description: Zero point for rotations around x axis in degrees.
                  type: number
                v:
                  description: Zero point for rotations around y axis in degrees.
                  type: number
            camera:
              description: Zero point for M2.
              type: object
              properties:
                x:
                  description: Zero point in x in mm.
                  type: number
                y:
                  description: Zero point in y in mm.
                  type: number
                z:
                  description: Zero point in z in mm.
                  type: number
                u:
                  description: Zero point for rotations around x axis in degrees.
                  type: number
                v:
                  description: Zero point for rotations around y axis in degrees.
                  type: number
        targets:
          description: >-
            Names of valid targets.
            Must include "CAM", "M1M3", "M2".
          type: array
          items:
            type: string
          minItems: 3
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
        targets_lut_coeffs:
          description: Target-specific LUT.
          type: object
          properties:
            CAM:
              description: Camera LUT
              type: object
              properites:
                elevation_rotation_coeffs:
                description: >-
                  Elevation/rotation compensation coefficients.
                  Rows are coefficients for x, y, z (um), u, v, w (deg).
                  The first index corresponds to powers of elevation and
                  the second index corresponds to powers of rotation.
                  Values are the coefficients in equation C_0_0
                  + C_0_1 * el + C_0_2 * el**2 + ... + C_1_0 * rot
                  + C_2_0 * rot**2 + ... + C_1_1 * el * rot
                  + C_1_2 * el**2 * rot + ... + C_2_1 * el * rot**2 + ...
                  where el is in deg.
                  Compensated value = uncompensated (user-specified) value
                    + elevation compensation
                    + azimuth compensation
                    + rotation compensation
                    + temperature compensation.
                type: array
                minItems: 6
                maxItems: 6
                items:
                  type: array
                  minItems: 1
                  items:
                    type: array
                    minItems: 1
                    items:
                      type: number
                azimuth_coeffs:
                description: >-
                  Azimuth compensation coefficients.
                  Rows are coefficients for x, y, z (um), u, v, w (deg).
                  Values are the coefficients in equation C0 + C1 az + C2 az^2 + ...,
                  where az is in deg.
                type: array
                minItems: 6
                maxItems: 6
                items:
                  type: array
                  minItems: 1
                  items:
                    type: number
                temperature_coeffs:
                description: >-
                  Temperature compensation coefficients.
                  Rows are coefficients for x, y, z (um), u, v, w (deg).
                  Values are the coefficients in equation C0 + C1 temp + C2 temp^2 + ...,
                  where temp is in C.
                type: array
                minItems: 6
                maxItems: 6
                items:
                  type: array
                  minItems: 1
                  items:
                    type: number
            M2:
              description: M2 LUT
              type: object
              properites:
                elevation_rotation_coeffs:
                description: >-
                  Elevation/rotation compensation coefficients.
                  Rows are coefficients for x, y, z (um), u, v, w (deg).
                  The first index corresponds to powers of elevation and
                  the second index corresponds to powers of rotation.
                  Values are the coefficients in equation C_0_0
                  + C_0_1 * el + C_0_2 * el**2 + ... + C_1_0 * rot
                  + C_2_0 * rot**2 + ... + C_1_1 * el * rot
                  + C_1_2 * el**2 * rot + ... + C_2_1 * el * rot**2 + ...
                  where el is in deg.
                  Compensated value = uncompensated (user-specified) value
                    + elevation compensation
                    + azimuth compensation
                    + rotation compensation
                    + temperature compensation.
                type: array
                minItems: 6
                maxItems: 6
                items:
                  type: array
                  minItems: 1
                  items:
                    type: array
                    minItems: 1
                    items:
                      type: number
                azimuth_coeffs:
                description: >-
                  Azimuth compensation coefficients.
                  Rows are coefficients for x, y, z (um), u, v, w (deg).
                  Values are the coefficients in equation C0 + C1 az + C2 az^2 + ...,
                  where az is in deg.
                type: array
                minItems: 6
                maxItems: 6
                items:
                  type: array
                  minItems: 1
                  items:
                    type: number
                temperature_coeffs:
                description: >-
                  Temperature compensation coefficients.
                  Rows are coefficients for x, y, z (um), u, v, w (deg).
                  Values are the coefficients in equation C0 + C1 temp + C2 temp^2 + ...,
                  where temp is in C.
                type: array
                minItems: 6
                maxItems: 6
                items:
                  type: array
                  minItems: 1
                  items:
                    type: number
        min_temperature:
          description: >-
            Minimum temperatures (C) for which the temperature model is valid.
            Below this temperature, terms above the first order are ignored;
            see RangedPolynomial for details.
          type: number
        max_temperature:
          description: >-
            Maximum temperatures (C) for which the temperature model is valid.
            Above this temperature, terms above the first order are ignored;
            see RangedPolynomial for details.
          type: number
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
