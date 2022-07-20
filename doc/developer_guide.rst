.. py:currentmodule:: lsst.ts.mtalignment

.. _lsst.ts.mtalignment.developer_guide:

###############
Developer Guide
###############

The MTAlignment CSC is implemented using `ts_salobj <https://github.com/lsst-ts/ts_salobj>`_ and `ts_hexrotcom <https://ts-hexrotcomm.lsst.io>`_.

.. _lsst.ts.mtalignment-api:

API
===

The primary classes are:

* `AlignmentCSC`: the CSC.
* `AlignmentModel`: contains most of the implementation and communicates with the 2TSA.

.. automodapi:: lsst.ts.mtalignment
   :no-main-docstr:

Build and Test
==============

This is a pure python package. There is nothing to build except the documentation.

.. code-block:: bash

    make_idl_files.py MTAlignment
    setup -r .
    pytest -v  # to run tests
    package-docs clean; package-docs build  # to build the documentation

Contributing
============

``ts_MTAlignment`` is developed at https://github.com/lsst-ts/ts_MTAlignment.
You can find Jira issues for this package using `labels=ts_MTAlignment <https://jira.lsstcorp.org/issues/?jql=project%20%3D%20DM%20AND%20labels%20%20%3D%20ts_MTAlignment>`_.
