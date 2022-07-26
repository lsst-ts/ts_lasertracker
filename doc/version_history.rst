.. py:currentmodule:: lsst.ts.MTAlignment

.. _lsst.ts.MTAlignment.version_history:

###############
Version History
###############

v0.2.0
------

* `CONFIG_SCHEMA`: update to version 3:

    * Add ``read_timeout`` and ``targets`` fields.
    * Rename ``t2sa_ip`` field to ``t2sa_host``.

* `AlignmentModel` bug fixes:
 
    * Fix an error in communication with the T2FA: most replies have an "ACK-300 " or "ERR-nnn " prefix.
    * ``send_command``: raise `T2SAError` for error replies from the T2FA.
    * ``wait_for_ready``: ignore all non-error replies except those that start with "READY".
      The old code insisted on "READY" or "EMP", but we see other replies, as well.
    * Rename all ``query_x`` methods to ``get_x``.
    * Replace the target-specific measure and get offset and get position methods with ``measure_target``, ``get_target_offset`` and ``get_target_position``.
      Note that the default reference frame for ``get_target_offset`` is the specified target, rather than "M1M3".
    * Make ``connected`` a property.
    * Make ``disconnect`` work even if already disconnected.

* `AlignmentCSC`: fix laserPower command; it was reading a non-existent command parameter.

v0.1.0
------

Initial release.

Updates from previous (unreleased) versions:

* Updated for ts_salobj 7.
* Added preliminary documentation, including this version history.
* Add a continuous integration Jenkinsfile.
* Build with pyproject.toml
* Add pre-commit support.
* Add conda recipe.
* Add Jenkinsfile.conda to build conda package.
* Update Jenkinsfile to stop overriding HOME with WORKSPACE.
* Minor fixes on executable entrypoint.
