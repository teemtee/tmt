Execute discovered tests in the provisioned environment using the
selected executor. The internal ``tmt`` executor is used by default.
It reports test progress and supports optional interactive debugging.

For each test, a separate directory is created for storing
artifacts related to the test execution. Its path is
constructed from the test name and it's stored under the
``execute/data`` directory. It contains a ``metadata.yaml``
file with the aggregated L1 metadata which can be used by the
test :tmt:story:`/spec/tests/framework`. In addition to supported
:tmt:story:`/spec/tests` attributes it also contains fmf ``name`` of
the test.

In each plan, the execute step must produce a ``results.yaml`` file
with results for executed tests. The format of the file is described
at :tmt:story:`/spec/results`.

.. _/plugins/execute/exit-first:

exit-first
----------

.. tmt:story:: /spec/plans/execute/exit-first
    :title: exit-first

    Stop execution after the first test failure or error

    Optional boolean attribute ``exit-first`` can be used to
    make the executor stop executing tests once a test
    failure or error is encountered.

    .. code-block:: yaml

        execute:
            how: tmt
            exit-first: true

.. _/plugins/execute/script:

script
------

.. tmt:story:: /spec/plans/execute/script
    :title: script

    Execute shell scripts

    .. code-block:: yaml

        # Run a simple smoke test
        execute:
            how: tmt
            script: tmt --help

    .. code-block:: yaml

        # Modify the default maximum duration
        execute:
            how: tmt
            script: a-long-test-suite
            duration: 3h

    .. code-block:: yaml

        # Run a script file, note that files are expected to be executable
        execute:
            script: ./run_tests.sh

.. _/plugins/execute/script/simple:

The simplest usage
^^^^^^^^^^^^^^^^^^

.. tmt:story:: /spec/plans/execute/script/simple
    :title: The simplest usage

    Simple use case should be super simple to write

    As the `how` keyword can be omitted when using the
    default executor you can just define the shell
    `script` to be run. This is how a minimal smoke test
    configuration for the `tmt` command can look like:

    .. code-block:: yaml

        execute:
            script: tmt --help

.. _/plugins/execute/script/several:

Multiple commands
^^^^^^^^^^^^^^^^^

.. tmt:story:: /spec/plans/execute/script/several
    :title: Multiple commands

    Multiple shell commands

    You can also include several commands as a list.
    Executor will run commands one-by-one and check exit
    code of each.

    .. code-block:: yaml

        execute:
            script:
              - dnf -y install httpd curl
              - systemctl start httpd
              - echo foo > /var/www/html/index.html
              - curl http://localhost/ | grep foo

.. _/plugins/execute/script/multi:

Multi-line script
^^^^^^^^^^^^^^^^^

.. tmt:story:: /spec/plans/execute/script/multi
    :title: Multi-line script

    Multi-line shell script

    Providing a multi-line shell script is also supported.
    Note that the first command with non-zero exit code will
    finish the execution. See the
    :tmt:story:`/spec/tests/test` key for details about default
    shell options.

    .. code-block:: yaml

        execute:
            script: |
                dnf -y install httpd curl
                systemctl start httpd
                echo foo > /var/www/html/index.html
                curl http://localhost/ | grep foo
