.. py:currentmodule:: lsst.ts.lasertracker

.. _lsst.ts.lasertracker.developer_guide:

###############
Developer Guide
###############

The LaserTracker CSC is implemented using `ts_salobj <https://github.com/lsst-ts/ts_salobj>`_ and `ts_tcpip <https://ts-tcpip.lsst.io>`_.

.. _lsst.ts.lasertracker-api:

API
===

The primary classes are:

* `AlignmentCSC`: the CSC.
* `T2SAModel`: contains most of the implementation and communicates with the 2TSA.

.. automodapi:: lsst.ts.lasertracker
   :no-main-docstr:

Build and Test
==============

This is a pure python package. There is nothing to build except the documentation.

.. code-block:: bash

    make_idl_files.py LaserTracker
    setup -r .
    pytest -v  # to run tests
    package-docs clean; package-docs build  # to build the documentation

Contributing
============

``ts_lasertracker`` is developed at https://github.com/lsst-ts/ts_lasertracker.
You can find Jira issues for this package using `labels=ts_lasertracker <https://jira.lsstcorp.org/issues/?jql=project%20%3D%20DM%20AND%20labels%20%20%3D%20ts_lasertracker>`_.
