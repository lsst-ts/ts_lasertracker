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
    default: "140.252.33.70"
  t2sa_port:
    description: port of T2SA instance.
    type: number
    default: 50000
"""
)
