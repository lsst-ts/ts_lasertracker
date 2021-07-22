__all__ = ["CONFIG_SCHEMA"]

import yaml


CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_MTAlignment/blob/master/schema/alignment.yaml
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: Alignment v1
description: Schema for MT Alignment CSC configuration files
type: object
properties:
  t2sa_ip:
    description: IP address of T2SA instance.
    type: string
    default: "127.0.0.1"
  t2sa_port:
    description: port of T2SA instance.
    type: number
    default: 50000
  num_iterations:
    description: number of times to repeat measurements of a point group
    type: number
    default: 1
  num_samples:
    description: number of times to sample each point within a single visit
    type: number
    default: 1
  randomize_points:
    description: if true, visit the SMRs in a random order
    type: boolean
    default: false
  station_lock:
    description: >-
      if true, prevents SpatialAnalyzer from automatically jumping stations
      if it detects that the tracker has drifted
    type: boolean
    default: false
  rms_tolerance:
    description: RMS least squares tolerance in mm
    type: number
    default: 0.05
  max_tolerance:
    description: maximum absolute tolerance  in mm
    type: number
    default: 1.0
  two_face_tolerance:
    description: >-
      maximum allowed divergence when measuring the same point using the
      tracker's two different "facings" in decimal degrees
    type: number
    default: 0.001
  rms_drift_tolerance:
    description: RMS least squares tolerance in mm
    type: number
    default: 0.05
  max_drift_tolerance:
    description: maximum absolute tolerance  in mm
    type: number
    default: 1.0
  power_lock:
    description: if true, enables the tracker’s camera (used to help search for SMRs).
    type: boolean
    default: true
  single_point_measurement_profile:
    description: name of Spatial Analyzer measurement profile
    type: string
    default: "Single Pt. To SA"
"""
)
