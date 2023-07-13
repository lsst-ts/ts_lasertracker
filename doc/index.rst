.. py:currentmodule:: lsst.ts.lasertracker

.. _lsst.ts.lasertracker:

###################
lsst.ts.lasertracker
###################

.. image:: https://img.shields.io/badge/Project Metadata-gray.svg
    :target: https://ts-xml.lsst.io/index.html#index-master-csc-table-lasertracker
.. image:: https://img.shields.io/badge/SAL\ Interface-gray.svg
    :target: https://ts-xml.lsst.io/sal_interfaces/LaserTracker.html
.. image:: https://img.shields.io/badge/GitHub-gray.svg
    :target: https://github.com/lsst-ts/ts_lasertracker
.. image:: https://img.shields.io/badge/Jira-gray.svg
    :target: https://jira.lsstcorp.org/issues/?jql=labels%3Dts_lasertracker

Overview
========

The LaserTracker CSC New River Kinematics T2SA laser alignment system.

User Guide
==========

Start the LaserTracker CSC
-------------------------

.. prompt:: bash

    run_lasertracker

.. _lsst.ts.lasertracker.configuration:

Configuration
-------------

Configuration is specified in `ts_config_mttcs <https://github.com/lsst-ts/ts_config_mttcs>`_ following `this schema <https://github.com/lsst-ts/ts_lasertracker/blob/develop/python/lsst/ts/lasertracker/config_schema.py>`_.

Simulator
---------

The CSC includes two simulation modes:

* 1: Run the spatial analyzer in simulation mode.
     This requires a TCP/IP connection to the T2SA.

* 2: Simple internal simulator.
     This requires no TCP/IP collection but is very simplistic,
     with no data analysis and canned responses to some queries.

To run using CSC's internal simulator:

.. prompt:: bash

    run_lasertracker --simulate={mode}

.. _lsst.ts.lasertracker.enable_with_eui:

Developer Guide
===============

.. toctree::
    developer_guide
    :maxdepth: 1

Version History
===============

.. toctree::
    version_history
    :maxdepth: 1
