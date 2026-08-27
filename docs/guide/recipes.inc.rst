.. _recipes:

Recipes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A recipe is a YAML file that captures a complete, static snapshot
of a ``tmt`` run after all dynamic evaluation has been resolved.
It stores preprocessed information about plans, tests and run
configuration, together with a link to the ``results.yaml`` files
from the original run.

tmt generates a recipe at the end of every run, and stores it as
``recipe.yaml`` in the :term:`run workdir`:

.. code-block::

    /var/tmp/tmt/run-001/recipe.yaml

The generated file can be reused to reproduce the run with the
same configuration, without a need to select plans or tests again
on the command line. See the :tmt:story:`/spec/recipe` specification
for the full description of the file format.


Examples
------------------------------------------------------------------

The following command runs the ``/plans/minimal`` plan from the
``tests/recipe/data`` metadata tree:

.. code-block:: shell

    tmt --root tests/recipe/data run \
        plan --name /plans/minimal

tmt writes ``recipe.yaml`` when the run finishes.
Inspect the generated file:

.. code-block:: shell

    cat /var/tmp/tmt/run-001/recipe.yaml

The generated recipe looks like this:

.. code-block:: yaml

    run:
        root: /path/to/tmt/tests/recipe/data
        remove: false
        environment: {}
        context: {}
    plans:
      - name: /plans/minimal
        summary: A minimal plan
        enabled: true
        order: 50
        environment:
            PLAN_ENV: plan_value
        discover:
            enabled: true
            phases:
              - name: default-0
                how: shell
                order: 50
                dist-git-source: false
                dist-git-download-only: false
                dist-git-install-builddeps: false
                keep-git-metadata: false
                url-content-type: git
                tests:
                  - name: script-00
                    test: echo "Execute script"
                    enabled: true
                    order: 50
                    manual: false
                    tty: false
                    duration: 1h
                    result: respect
            tests:
              - name: /script-00
                discover-phase: default-0
                test: echo "Execute script"
                path: /default-0/tests
                enabled: true
                order: 50
                framework: shell
                manual: false
                tty: false
                duration: 1h
                restart-max-count: 1
                restart-with-reboot: false
                result: respect
                serial-number: 1
        provision:
            enabled: true
            phases:
              - name: default-0
                how: container
                order: 50
                become: false
                environment:
                    PROVISION_ENV: provision_value
                force-pull: false
                image: fedora
                pull-attempts: 5
                pull-interval: 5
                stop-time: 1
                user: root
        prepare:
            enabled: true
            phases:
              - name: default-0
                how: shell
                order: 50
        execute:
            enabled: true
            phases:
              - name: default-0
                how: tmt
                order: 50
                duration: 1h
                exit-first: false
                ignore-duration: false
                interactive: false
                restraint-compatible: false
                no-progress-bar: false
            results-path: plans/minimal/execute/results.yaml
        report:
            enabled: true
            phases:
              - name: default-0
                how: display
                order: 50
                display-guest: auto
        finish:
            enabled: true
            phases:
              - name: default-0
                how: shell
                order: 50
        cleanup:
            enabled: true
            phases:
              - name: default-0
                how: tmt
                order: 50


Each plan lists its steps. A step that ran in the original run has
``enabled: true``.

Reproduce the run from that recipe:

.. code-block:: shell

    tmt run --recipe /var/tmp/tmt/run-001/recipe.yaml

A new run is created from the recipe. The original workdir is left
unchanged.

If you need to enable the steps that were disabled in the original
run, you can edit the recipe and set the ``enabled`` flag to ``true``,
or use command line options to enable/disable specific steps:

.. code-block:: shell

    tmt run --recipe recipe.yaml --all
    tmt run --recipe recipe.yaml --until report


The following command runs the ``/plans/local`` plan from the
``tests/recipe/data`` metadata tree:

.. code-block:: shell

    tmt --root tests/recipe/data -c distro=fedora run \
        -e RUN_ENV=run_value \
        plan --name /plans/local

The generated recipe looks like this:

.. code-block:: yaml

    run:
        root: /path/to/tmt/tests/recipe/data
        remove: false
        environment:
            RUN_ENV: run_value
        context:
            distro:
              - fedora
    plans:
      - name: /plans/local
        summary: A local plan
        enabled: true
        order: 50
        link:
          - relates: https://something.org/related
        environment:
            PLAN_ENV: plan_value
        discover:
            enabled: true
            phases:
              - name: discover-fmf
                how: fmf
                order: 50
                dist-git-download-only: false
                dist-git-init: false
                dist-git-install-builddeps: false
                dist-git-merge: false
                dist-git-remove-fmf-root: false
                dist-git-source: false
                fmf-id: false
                modified-only: false
                prune: false
                sync-repo: false
                url-content-type: git
              - name: discover-shell
                how: shell
                order: 50
                dist-git-download-only: false
                dist-git-install-builddeps: false
                dist-git-source: false
                keep-git-metadata: false
                url-content-type: git
                tests:
                  - name: /shell-test
                    test: /bin/true
                    enabled: true
                    order: 50
                    manual: false
                    tty: false
                    duration: 1h
                    result: respect
            tests:
              - name: /discover-fmf/tests/first
                discover-phase: discover-fmf
                test: ./test.sh
                path: /discover-fmf/tests
                summary: First test
                enabled: true
                order: 50
                framework: beakerlib
                manual: false
                tty: false
                duration: 5m
                restart-max-count: 1
                restart-with-reboot: false
                serial-number: 1
                require:
                  - url: https://github.com/beakerlib/test
                    name: /very/deep/file
                    type: library
                environment:
                    TEST_ENV: test_value
                result: respect
              - name: /discover-fmf/tests/second
                discover-phase: discover-fmf
                test: echo SECOND_TEST
                path: /discover-fmf/tests
                summary: Second test
                enabled: true
                order: 50
                framework: shell
                manual: false
                tty: false
                duration: 5m
                restart-max-count: 1
                restart-with-reboot: false
                serial-number: 2
                result: respect
                check:
                  - how: dmesg
                    enabled: true
                    result: info
                    failure-pattern:
                      - 'Call Trace:'
                      - \ssegfault\s
              - name: /discover-shell/shell-test
                discover-phase: discover-shell
                test: /bin/true
                path: /discover-shell/tests
                enabled: true
                order: 50
                framework: shell
                manual: false
                tty: false
                duration: 1h
                restart-max-count: 1
                restart-with-reboot: false
                serial-number: 3
                result: respect
        provision:
            enabled: true
            phases:
              - name: default-0
                how: container
                order: 50
                become: false
                environment:
                    PROVISION_ENV: provision_value
                force-pull: false
                image: fedora
                pull-attempts: 5
                pull-interval: 5
                stop-time: 1
                user: root
        prepare:
            enabled: true
            phases:
              - name: default-0
                how: shell
                order: 50
                script:
                  - echo "Prepare phase"
        execute:
            enabled: true
            phases:
              - name: Execute phase
                how: tmt
                order: 50
                duration: 1h
                exit-first: false
                ignore-duration: false
                interactive: false
                restraint-compatible: false
                no-progress-bar: false
            results-path: plans/local/execute/results.yaml
        report:
            enabled: true
            phases:
              - name: default-0
                how: display
                order: 50
                display-guest: auto
        finish:
            enabled: true
            phases:
              - name: default-0
                how: shell
                order: 50
                script:
                  - echo "Finish phase"
        cleanup:
            enabled: true
            phases:
              - name: default-0
                how: tmt
                order: 50

The ``discover`` step contains a ``tests`` list. Tests to execute
are taken from that list, not rediscovered from the discover phases.
The discover phases still run, for example to fetch remote git
repositories, because tests may need external files or library
dependencies. Each test must keep the ``name`` and ``discover-phase``
keys. The ``discover-phase`` key must match the phase that discovered
the test.

The ``execute`` step stores ``results-path`` as a path relative to
the original :term:`run workdir`.


Edit a Recipe
------------------------------------------------------------------

The generated recipe can be edited by hand or with a script. Copy
the file first so that the original run stays intact:

.. code-block:: shell

    cp /var/tmp/tmt/run-581/recipe.yaml ./recipe.yaml

Adjust the copy, then execute it:

.. code-block:: shell

    tmt run --recipe ./recipe.yaml

Select Tests
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Tests that should run are listed under the plan's ``discover``
step, in the ``tests`` list. Remove entries from that list to keep
only the tests that should be reexecuted.

You can use ``results-path`` to inspect outcomes from the original
run and decide which tests to keep. That key is informational only
and is ignored when the recipe is executed. The new run always writes
fresh results.

Filter the ``tests`` list with a custom script that reads the
``results.yaml`` file described by :tmt:story:`/spec/results`,
or use the `tmt-recipe-tool`__. The tool takes a recipe and its
associated results and writes a new recipe that contains only
the tests matching a filter expression. Results can come from the
local results file or from a ReportPortal launch when the recipe
report phase uses :ref:`/plugins/report/reportportal`.

Install the tool from the `teemtee/tools`__ repository, then see
``tmt-recipe-tool --help`` for the full list of options. The
default filter keeps failed and errored tests:

.. code-block:: shell

    tmt-recipe-tool -i recipe.yaml -o filtered.yaml

Keep only tests that passed:

.. code-block:: shell

    tmt-recipe-tool -i recipe.yaml -o filtered.yaml -f 'result: pass'

Keep failed tests, or tests whose name matches a pattern:

.. code-block:: shell

    tmt-recipe-tool -i recipe.yaml -o filtered.yaml \
        -f 'result: fail | name: .*/smoke.*'

Filter and rerun the matching tests immediately:

.. code-block:: shell

    tmt-recipe-tool -i recipe.yaml --run -f 'result: pass'

Use ReportPortal results instead of the local file:

.. code-block:: shell

    tmt-recipe-tool -i recipe.yaml -o filtered.yaml --use-reportportal \
        -f 'result: failed & defect: product_bug'

Filtering uses fmf expression `syntax`__. Matching is
case-insensitive and values are regular expressions. Result
status names are not mapped between sources: tmt results use
``pass``, ``fail``, ``warn`` and ``error``, while ReportPortal
uses ``passed``, ``failed`` and ``skipped``. The default filter
includes both tmt ``fail``/``error`` and ReportPortal
``failed``.

__ https://github.com/teemtee/tools/tree/main/tmt-recipe-tool
__ https://github.com/teemtee/tools
__ https://fmf.readthedocs.io/en/stable/modules.html#fmf.filter
