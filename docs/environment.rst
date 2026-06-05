.. _environment-variable-precedence:

:tocdepth: 2

Environment precedence
~~~~~~~~~~~~~~~~~~~~~~

.. important::

    The following is the description of how things are. It is **not**
    describing the desired state, for that see notes and progress report
    in the `Document the order of precedence of environment variable sources`__
    issue. Individual sets of variables will switch places as we progress
    towards the desired ordering.

    __ https://github.com/teemtee/tmt/issues/4241

The following sections describe various sets of environment variables
exposed by tmt, in their order of precedence from least to greatest: the
last listed variables override variables from previous set.

1. User-provided guest environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As set via :ref:`environment </plugins/provision/common-keys>` key of
individual ``provision`` phases. Applies to user commands executed on
the given guest.

2. User-provided test environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As set via :tmt:story:`environment </spec/tests/environment>` key of
individual tests.

3. User-controlled plan environment file
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Environment variables loaded from a file the ``TMT_PLAN_ENVIRONMENT_FILE``
environment variable points at.

4. User-provided plan environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

4.1. ``environment-file`` plan key
::::::::::::::::::::::::::::::::::

Environment variables loaded from files listed in the
:tmt:story:`environment </spec/plans/environment-file>` plan key.

4.2. ``environment`` plan key
:::::::::::::::::::::::::::::

Environment variables set via
:tmt:story:`environment </spec/plans/environment>` plan key.

5. Environment inherited from the importing plan
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. note::

    These sets of environment variables exist only when the plan has been
    :tmt:story:`imported </spec/plans/import-plans>`. Local plans do not
    have an importing plan, and have no plan to inherit environment from.

5.1. Importing plan's ``environment-file`` plan key
:::::::::::::::::::::::::::::::::::::::::::::::::::

Environment variables loaded from files listed in the
importing plan's :tmt:story:`environment </spec/plans/environment-file>`
plan key.

5.2. Importing plan's ``environment`` plan key
::::::::::::::::::::::::::::::::::::::::::::::

Environment variables set via
importing plan's :tmt:story:`environment </spec/plans/environment>` plan
key.

5.3. Importing plan's importing plan
::::::::::::::::::::::::::::::::::::

This set is the recursive aspect of the inherited environment:

* An imported plan ``/A`` inherits the aforementioned environment variables
  from its importing plan, ``/B``.
* Said importing plan, ``/B``, might have been an imported plan as well,
  imported by a plan called ``/C``. This makes ``/C`` the importing plan
  of ``/B``, and ``/B`` itself inherits the aforementioned environment
  variables from its importing plan, ``/C``. These variables are then
  inherited by ``/A``.

The chain of importing plans is followed to its end, until there is no
importing plan to inherit from.

6. Command-line options of ``tmt run`` command
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

6.1. ``--environment-file`` option
::::::::::::::::::::::::::::::::::

6.2. ``--environment`` option
:::::::::::::::::::::::::::::

.. note::

    This set includes also files with environment variables when such
    files are given to ``tmt run`` using the ``@<filepath>`` form.

7. Run environment
^^^^^^^^^^^^^^^^^^

7.1. Environment from the previous run
::::::::::::::::::::::::::::::::::::::

.. note::

    Applies to ``tmt run`` command alone, and only when ``tmt run`` is
    reusing an existing workdir, populated by a previous ``tmt run``
    command.

Environment variables given to the previous run via ``--environment-file``
or ``--environment`` variables.

7.2. ``--environment-file`` option
::::::::::::::::::::::::::::::::::

7.3. ``--environment`` option
:::::::::::::::::::::::::::::

.. note::

    This set includes also files with environment variables when such
    files are given to ``tmt run`` using the ``@<filepath>`` form.

8. Variables exposed by tmt, run, plan, steps, and plugins
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These are the strongest sets of environment variables, always overriding
preexisting ones.

The variables here are not ordered by their order of precedence. They
are owned and exposed by various tmt internal components and subsystems,
and they do not conflict with each other. From the user perspective, they
behave as a single set which overrides variables from the previous sets,
and their internal ordering is not relevant.

Instead, they are grouped by plan steps, with notes mentioning possible
limitations.

* ``discover``
    * ``TMT_PLAN_DATA``
    * ``TMT_PLAN_ENVIRONMENT_FILE``
    * ``TMT_PLAN_SOURCE_SCRIPT``
    * ``TMT_TREE``
    * ``TMT_VERSION``

* ``provision``
    * ``TMT_PLAN_DATA``
    * ``TMT_PLAN_ENVIRONMENT_FILE``
    * ``TMT_PLAN_SOURCE_SCRIPT``
    * ``TMT_TREE``
    * ``TMT_VERSION``

* ``prepare``
    * ``REBOOTCOUNT``
    * ``RSTRNT_REBOOTCOUNT``
    * ``TMT_TEST_PIDFILE``
    * ``TMT_TEST_PIDFILE_LOCK``
    * ``TMT_TEST_PIDFILE_ROOT``
    * ``TMT_PLAN_DATA``
    * ``TMT_PLAN_ENVIRONMENT_FILE``
    * ``TMT_PLAN_SOURCE_SCRIPT``
    * ``TMT_PREPARE_SHELL_URL_REPOSITORY``

      .. note::

         Only to the ``prepare/shell`` phases.
    * ``TMT_REBOOT_REQUEST``
    * ``TMT_REBOOT_COUNT``
    * ``TMT_TEST_RESTART_COUNT``
    * ``TMT_TOPOLOGY_BASH``
    * ``TMT_TOPOLOGY_YAML``
    * ``TMT_TREE``
    * ``TMT_VERSION``

* ``execute``
    * ``BEAKERLIB_DIR``

      .. note::

         Only when a test with the ``beakerlib`` framework runs.
    * ``BEAKERLIB_COMMAND_SUBMIT_LOG``

      .. note::

         Only when a test with the ``beakerlib`` framework runs.
    * ``BEAKERLIB_COMMAND_REPORT_RESULT``

      .. note::

         Only when a test with the ``beakerlib`` framework runs.
    * ``IN_PLACE_UPGRADE``

      .. note::

        To the ``execute/upgrade`` phases only.
    * ``RSTRNT_REBOOTCOUNT``
    * ``RSTRNT_TASKNAME``
    * ``TESTID``

      .. note::

         Only when a test with the ``beakerlib`` framework runs.
    * ``TMT_TEST_PIDFILE``
    * ``TMT_TEST_PIDFILE_LOCK``
    * ``TMT_TEST_PIDFILE_ROOT``
    * ``TMT_PLAN_DATA``
    * ``TMT_PLAN_ENVIRONMENT_FILE``
    * ``TMT_PLAN_SOURCE_SCRIPT``
    * ``TMT_REBOOT_COUNT``
    * ``TMT_REBOOT_REQUEST``
    * ``TMT_RESTRAINT_COMPATIBLE``
    * ``TMT_SOURCE_DIR``
    * ``TMT_TEST_DATA``
    * ``TMT_TEST_INVOCATION_PATH``
    * ``TMT_TEST_ITERATION_ID``
    * ``TMT_TEST_METADATA``
    * ``TMT_TEST_NAME``
    * ``TMT_TEST_RESTART_COUNT``
    * ``TMT_TEST_SERIAL_NUMBER``
    * ``TMT_TEST_SUBMITTED_FILES``
    * ``TMT_TOPOLOGY_BASH``
    * ``TMT_TOPOLOGY_YAML``
    * ``TMT_TREE``
    * ``TMT_VERSION``

* ``finish``
    * ``REBOOTCOUNT``
    * ``RSTRNT_REBOOTCOUNT``
    * ``TMT_TEST_PIDFILE``
    * ``TMT_TEST_PIDFILE_LOCK``
    * ``TMT_TEST_PIDFILE_ROOT``
    * ``TMT_PLAN_DATA``
    * ``TMT_PLAN_ENVIRONMENT_FILE``
    * ``TMT_PLAN_SOURCE_SCRIPT``
    * ``TMT_PREPARE_SHELL_URL_REPOSITORY``

      .. note::

         Only to the ``finish/shell`` phases.
    * ``TMT_REBOOT_REQUEST``
    * ``TMT_REBOOT_COUNT``
    * ``TMT_TEST_RESTART_COUNT``
    * ``TMT_TOPOLOGY_BASH``
    * ``TMT_TOPOLOGY_YAML``
    * ``TMT_TREE``
    * ``TMT_VERSION``


Consumed by tmt itself
~~~~~~~~~~~~~~~~~~~~~~

.. note::

    The following environment variables are set for and consumed by tmt
    process itself, and never propagated to user environment.

* ``NO_COLOR``
* ``TMT_BOOT_TIMEOUT``
* ``TMT_CONNECT_TIMEOUT``
* ``TMT_CONFIG_DIR``
* ``TMT_DEBUG``
* ``TMT_DOWNLOAD_ATTEMPTS``
* ``TMT_DOWNLOAD_INTERVAL``
* ``TMT_EXPOSABLE_RUNNER_DEVICES``
* ``TMT_FEELING_SAFE``
* ``TMT_FORCE_COLOR``
* ``TMT_GIT_CLONE_ATTEMPTS``
* ``TMT_GIT_CLONE_INTERVAL``
* ``TMT_GIT_CLONE_TIMEOUT``
* ``TMT_GIT_CREDENTIALS_URL_<suffix>``
* ``TMT_GIT_CREDENTIALS_VALUE_<suffix>``
* ``TMT_NO_COLOR``
* ``TMT_OUTPUT_WIDTH``
* ``TMT_PLUGIN_${STEP}_${PLUGIN}_${OPTION}``
* ``TMT_PLUGINS``
* ``TMT_POLICY_FILE``
* ``TMT_POLICY_NAME``
* ``TMT_POLICY_ROOT``
* ``TMT_REBOOT_TIMEOUT``
* ``TMT_REPORT_ARTIFACTS_URL``
* ``TMT_RETRY_SESSION_BACKOFF_FACTOR``
* ``TMT_RETRY_SESSION_BACKOFF_MAX``
* ``TMT_RETRY_SESSION_RETRIES``
* ``TMT_SCRIPTS_DIR``
* ``TMT_SHOW_TRACEBACK``
* ``TMT_SSH_*``
* ``TMT_STATE_FORMAT``
* ``TMT_WORKDIR_ROOT``
