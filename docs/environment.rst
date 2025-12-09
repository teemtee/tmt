.. _environment-variable-precedence:

:tocdepth: 2

Environment precedence
~~~~~~~~~~~~~~~~~~~~~~

.. warning::

    Just a draft, adding my notes, moving sections around, etc. very
    fluid.

.. todo::

    AFAICT, the rough order of precedence, as of now, is something like the following:

    * ``provision[].environment``
    * ``test[].environment``
    * "plan environment"
        * ``$TMT_PLAN_ENVIRONMENT_FILE``
        * plan ``environment-file`` key
        * plan ``environment`` key
        * importing plan "native" environment
            * importing plan ``environment-file`` key
            * importing plan ``environment`` key
            * importing plan importing plan ...
        * run environment saved in the workdir (``--environment`` and ``--environment-file`` from previous invocations)
        * ``tmt run --environment``
        * ``tmt run --environment-file``
        * plan intrinsic variables: ``TMT_VERSION``, ``TMT_TREE``, ...
    * plugin intrinsic variables
        * abort context
        * reboot context
        * restart context
        * pidfile context
        * restraint context
        * test framework
        * ...

.. todo::

    This should be the desired order of precedence:

    * ``test[].environment``
    * plan ``environment-file`` key
    * plan ``environment`` key
    * importing plan "native" environment
        * importing plan ``environment-file`` key
        * importing plan ``environment`` key
        * importing plan importing plan ...
    * ``provision[].environment``
    * ``$TMT_PLAN_ENVIRONMENT_FILE``
    * command-line input:
        * ``tmt run``
            * run environment saved in the workdir (``--environment-file`` and ``--environment`` from previous invocations)
            * ``tmt run --environment-file``
            * ``tmt run --environment``
        * ``tmt * export``
            * ``tmt * export --environment-file``
            * ``tmt * export --environment``
        * ``tmt try``
            * ``tmt try --environment-file``
            * ``tmt try --environment``
    * plugin intrinsic variables
        * abort context
        * reboot context
        * restart context
        * pidfile context
        * restraint context
        * test framework
        * plan intrinsic variables: ``TMT_VERSION``, ``TMT_TREE``, ...
        * ...

.. todo::

    .. code-block::

        # Asorted list of environment sources

        External sources
            run: --environment and --environment-file CLI options
            plan: environment and environment-file fmf keys
            importing plan: environment fmf key of the importing plan
            provision phases ("per-guest environment"): environment fmf key, --environment CLI option
            test: environment fmf key

        Internal sources
            ~~plugin action itself - test name, test data, plan data, ...~~
            ~~test framework~~
            ~~invocation contexts - reboot, restart, abort, pidfile, restraint, ...~~

.. todo::

    Plan environment is actually dumped into test environment, so
    it apparently overrides the test environment. In any case, it should
    be added explicitly into the final environment, not sneaked into via
    test.

    .. code-block:: python

        # (tmt/steps/discover/__init__.py)

        # Update test environment with plan environment
        test.environment.update(self.plan.environment)

    "Plan environment" consistst of multiple sources, in this order:

    * plan environment file, ``$TMT_PLAN_ENVIRONMENT_FILE``
    * plan ``environment-file`` key  (```plan: environment and environment-file fmf keys`` source)
    * plan ``environment`` key  (```plan: environment and environment-file fmf keys`` source)
    * importing plan "native" environment (``importing plan: environment fmf key of the importing plan`` source)
        * ``environment-file`` key
        * ``environment`` key
        * importing plan's "native" environment
    * run ``--environment`` option  (``run: --environment and --environment-file CLI options`` source)
    * run ``--environment-file`` option  (``run: --environment and --environment-file CLI options`` source)
    * run ``environment`` property (seems to be the duplication of the previous two inputs)
    * plan intrinsic variables: ``TMT_VERSION``, ``TMT_TREE``, ...

.. todo::

    ``TMT_SOURCE_DIR`` is added to test environment:

    .. code-block:: python

        # (tmt/steps/discover/fmf.py)

        for test in self._tests:
            test.environment['TMT_SOURCE_DIR'] = EnvVarValue(sourcedir)

        # (tmt/steps/discover/shell.py)

        if self.data.dist_git_source:
            test.environment['TMT_SOURCE_DIR'] = EnvVarValue(sourcedir)

.. todo::

    Document order of precedence for ``environment`` key and
    ``environment`` CLI option in case of ``provision`` phases

.. todo::

    Send out an announcement.

.. important::

    The following is the draft of how things should be. It is incomplete,
    and it does contain several notes, but this is what would document
    the precedence.

Listing environment variable sources in their order of precedence, from
the least preferred to the strongest ones.

1. User-provided guest-specific environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As set via :ref:`environment </plugins/provision/common-keys>` key of
individual ``provision`` phases. Applies to user commands executed on
the given guest.

.. todo::

    "Applies" is a strong word, we need to fix plugins that do not do
    this but should, like ``shell`` - and document those that will not
    expose the environment, like ``ansible``.

2. User-provided test-specific environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As set via :ref:`environment </spec/tests/environment>` key of individual
tests.

X. User-provided plan-specific environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. todo::

    Plan environment consists of several inputs, and it is injected into
    individual test environment mappings, efefctively placing all of them
    there with on this level.

Last. Variables set by tmt, run, plan, steps, and plugins
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These are the strongest sources, always overriding any preexisting
variables.

.. note::

    The variables here are not ordered by their order of precedence, as
    they do appear sharing the same level to the user code. Individual
    sources contribute their distinct subsets of variables.

* For all steps
    * ``TMT_TREE``
    * ``TMT_PLAN_DATA``
    * ``TMT_PLAN_ENVIRONMENT_FILE``
    * ``TMT_VERSION``

* For the ``discover`` step
    * ``TMT_SOURCE_DIR`` (note: very fishy way of setting it by injecting into ``Test.environment``)

* For the ``execute`` step
    * ``TMT_TEST_NAME``
    * ``TMT_TEST_INVOCATION_PATH``
    * ``TMT_TEST_SUBMITTED_FILES``
    * ``TMT_TEST_DATA``
    * ``TMT_TEST_SERIAL_NUMBER``
    * ``TMT_TEST_ITERATION_ID``
    * ``TMT_TEST_METADATA``
    * ``TMT_RESTRAINT_COMPATIBLE`` (note: extend scope to ``prepare|execute|finish``)
    * ``RSTRNT_TASKNAME`` (note: extend scope to ``prepare|execute|finish``)

* For the ``execute`` step with the ``beakerlib`` framework
    * ``BEAKERLIB_DIR``
    * ``BEAKERLIB_COMMAND_SUBMIT_LOG``
    * ``BEAKERLIB_COMMAND_REPORT_RESULT``
    * ``TESTID``

* For the ``execute/upgrade`` phase
    * ``IN_PLACE_UPGRADE``

* For the ``prepare``, ``execute``, and ``finish`` step
    * ``TMT_REBOOT_REQUEST``
    * ``TMT_REBOOT_COUNT``
    * ``REBOOTCOUNT``
    * ``RSTRNT_REBOOTCOUNT``
    * ``TMT_TEST_RESTART_COUNT``
    * ``TMT_TOPOLOGY_BASH``
    * ``TMT_TOPOLOGY_YAML``
    * ``TMT_TEST_PIDFILE``
    * ``TMT_TEST_PIDFILE_LOCK``
    * ``TMT_TEST_PIDFILE_ROOT``

* For the ``prepare/shell`` and ``finish/shell`` phases
    * ``TMT_PREPARE_SHELL_URL_REPOSITORY``
    * ``TMT_FINISH_SHELL_URL_REPOSITORY``


Consumed by tmt itself
~~~~~~~~~~~~~~~~~~~~~~

.. note::

    The following environment variables are set for and consumed by tmt
    process itself, and never propagated to user environment.

* ``TMT_DEBUG``
* ``TMT_PLUGINS``
* ``TMT_FEELING_SAFE``
* ``TMT_CONFIG_DIR``
* ``TMT_WORKDIR_ROOT``
* ``NO_COLOR``
* ``TMT_NO_COLOR``
* ``TMT_FORCE_COLOR``
* ``TMT_SHOW_TRACEBACK``
* ``TMT_OUTPUT_WIDTH``
* ``TMT_GIT_CREDENTIALS_URL_<suffix>``
* ``TMT_GIT_CREDENTIALS_VALUE_<suffix>``
* ``TMT_GIT_CLONE_ATTEMPTS``
* ``TMT_GIT_CLONE_INTERVAL``
* ``TMT_GIT_CLONE_TIMEOUT``
* ``TMT_BOOT_TIMEOUT``
* ``TMT_CONNECT_TIMEOUT``
* ``TMT_REBOOT_TIMEOUT``
* ``TMT_SCRIPTS_DIR``
* ``TMT_SSH_*``
* ``TMT_REPORT_ARTIFACTS_URL``
* ``TMT_POLICY_FILE``
* ``TMT_POLICY_NAME``
* ``TMT_POLICY_ROOT``
* ``TMT_PLUGIN_${STEP}_${PLUGIN}_${OPTION}``
