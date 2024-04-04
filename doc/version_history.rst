.. py:currentmodule:: lsst.ts.lasertracker

.. _lsst.ts.lasertracker.version_history:

###############
Version History
###############

v0.8.0
------

* In ``laser_tracker_csc``:

  * update target name format to match the latest version of T2SA.

  * reset measurement index to 1 when starting.

  * update measure alignment method to handle situation where one or more measurements failed.

  * fix setting azimuth and camera angles when values are close to zero.

  * update how CSC handle laser status command.

  * move code in handle_summary_state to begin_start to make sure the CSC connects to T2SA before it transitions to DISABLED.

  * update telemetry loop to send CSC to fault if there is an error.

* In ``mock/mock_t2sa``:

  * add canned response to command to increment measurement index.

  * update response from the STAT command.

* In ``t2sa_model``:

  * fix command to increment measurement index and to set measuremement index.

  * update get_status to return BUSY if error is either InstrumentNotReady or CommandRejectedBusy.

  * update how the model handles the response from the STAT command.

  * update error message to remove reference to disconnection for the server when there's an error.

* In ``utils.py``, update MEASURE_REGEX to account for new =separator.

* Add new ErrorCodes enumeration.

* Fix issue with mypy.

* Update .gitignore with latest ts-pre-commit-config setup.

v0.7.1
------

* Add ``TMA_CENTRAL`` and ``TMA_UPPER`` as targets for Laser Tracker measurements.

v0.7.0
------

* In ``mock/mock_t2sa``, update ``MockT2SA`` to work with ``ts_tcpip>=2.0``.

v0.6.0
------

* In ``mock/mock_t2sa.py``, update mock controller to more closely resemble the latest version of T2SA.

  In addition to implementing API changes, makes some improvements in how the mock operates.

* Modernize Jenkinfile to use shared library.

* Update package to use ts-pre-commit-hook.

* Update pyproject to remove black and flake8 checks when running pytest.

* In ``utils.py``, Update ``SINGLE_POINT_MEASURE_REGEX``, ``OFFSET_MEASURE_REGEX`` and add new ``MEASURE_REGEX``.

* In ``t2sa_model.py``:

  * Refactor ``_basic_send_command`` to split the operation between writing the command to the controller and waiting for the reply.

    This also adds the possibility of writing a command and not waiting for the reply.

  * Remove ``wait_for_ready`` method.

    This method was introduced based on a previous iteration of the T2SA operation model, where all command would work in a "fire and forget" mode and the client would wait for the status to be "READY" again before it could operate the system.
    A recent change to the software changed this behavior such that, now, T2SA sends command acknowledgements with the result of the operation.

  * Change ``get_status`` signature to remove option to lock or not the controller.

    All command now lock the writer and the user can decide if they want to wait for a reply or not.

  * Update ``halt`` model to write the halt command without waiting for the reply, then acquiring the communication lock and waiting for the reply.

  * Update ``get_target_offset`` with the correct order of the components.

* In ``laser_tracker_csc.py``:

  * Update LaserTracker CSC to get the telescope position from the ``MTMount`` telemetry and set the value in the controller.

  * Update ``do_align`` method to send IN_PROGRESS acknowledgements while the measurement is ongoing (to avoid command timeouts).

  * Add new ``get_target_name`` method that will return a string formatted with the target name.

    This is the name T2SA sets for the targets (or groups) based on the position of the telescope and the "group name".

  * Update ``do_measureTarget`` to send IN_PROGRESS acknowledgements and set the telescope position in the controller before making a measurement .

  * Update ``do_healthCheck`` to send ACK_INPROGRESS.

  * Update ``measure_alignment`` to use the new ``get_target_name`` to retrieve the name of the component as expected by T2SA and to force output the events.

  * Update ``handle_summary_state`` to log more information.

  * Update ``configure`` method to log the configuration.

v0.5.3
------

* fill newly available t2saStatus and laserStatus

v0.5.2
------

* pre-commit: update the version of black, isort, and mypy.

v0.5.1
------

* `CONFIG_SCHEMA`: fixed the checking for required fields.
  There were errors in the schema that broke the checking.
* ``Jenkinsfile``: stop running as root.

v0.5.0
------

* Rename from ts_MTAlignment to ts_lasertracker and make an indexed component.
  This requires ts_xml 15.

  * Rename AlignmentCSC to LaserTrackerCsc.
  * Rename AlignmentModel to T2SAModel.

v0.4.1
------

* pre-commit: update mypy version and flake8 repo.

v0.4.0
------

* Update for improved T2SA API which changes the EMP reply to a standard ERR reply and deletes the colon after ERR-xxx.
* Refine `AlignmentModel`:

  * Modify ``send_command`` to raises T2SAError if the system is busy.
    This is the natural thing to do, now that the T2SA reports busy as a standard error.
  * Rename ``check_status`` to ``get_status`` and update it as follows:

    * Return "BUSY" if busy (instead of "EMP", the old, confusing value).
    * Add an optional ``do_lock`` argument, so it can be called by ``wait_for_ready``.

* Update `T2SAErrorCode` enum with latest error codes and names provided by the T2SA vendor.
* Update `MockT2SA` to report approximately correct error codes.
  It is more work than it's worth to get them exactly right, and the CSC ignores the codes, other than checking for CommandRejectedBusy.

v0.3.0
------

* Add new utils module.

  This module contains some utility classes and functions to support mocking the T2SA behavior (``BodyRotation`` and ``CartesianCoordinate``) and to support parsing measurement messages from T2SA  (``parse_offsets`` and ``parse_single_point_measurement``).

  Also adds a ``Target`` enumeration to support the ``align`` command.
  In general these would go in ``ts_idl`` package.
  Nevertheless, it is more likely that we should remove the use of an enumeration in favor of a string, since this is how the code handle the data internally, and it will make updating the "targets" more easily.

* Add new submodule ``mock/mock_t2sa_target.py`` that implements ``MockT2SATarget`` class.

  This class represent a measuring "target" in the T2SA system.
  It contains the cartesian coordinates, rotation and radius of the body, plus definition of the location of the measuring targets. 
  With this information it is possible to compute the location of each individual target or the entire body in the cartesian coordinate system, plus the respective rotations.

* Move ``mock_t2sa`` module to the new submodule ``mock``.

* Major overhaul on ``MockT2SA``.

  * Implement new mechanism to handle commands in parallel with the canned replies.
    Now each command can execute a method in the class passing named arguments.
    Methods that receive arguments must have a paired command arg parser, which uses regular expressions with named matches to parse the input data.

  * Use MockT2SATarget to compute the groups and target positions and offsets.
  * Listen to telemetry from m1m3, camera hexapod and m2 hexapod to alter the position of the targets.
  * Add handlers for the majority of the commands with more realistic responses.
  * Add type annotations.

* Add type annotations to ``AlignmentModel``.

* Update test model to expand a bit the existing tests.

* Overhaul in ``AlignmentCSC``.

  * Fix issues with several of the existing commands.

  * Add type annotations.

* Expand ``AlignmentCSC`` unit tests implementing tests for the majority of the commands.

* Add scipy dependency to conda package.

v0.2.0
------

* ``CONFIG_SCHEMA``: update to version 3:

    * Add ``read_timeout`` and ``targets`` fields.
    * Rename ``t2sa_ip`` field to ``t2sa_host``.

* ``AlignmentModel`` bug fixes:
 
    * Fix an error in communication with the T2FA: most replies have an "ACK-300 " or "ERR-nnn " prefix.
    * ``send_command``: raise ``T2SAError`` for error replies from the T2FA.
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
