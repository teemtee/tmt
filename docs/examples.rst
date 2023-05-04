.. _examples:

======================
    Examples
======================

Let's have a look at a couple of real-life examples!

You can obtain detailed list of available options for each command
by invoking it with ``--help``. In order to control the verbosity
of the output use ``--verbose`` and ``--quiet``. To display
implementation details for debugging use the ``--debug`` option.
See :ref:`/stories/cli/common` options for details.

Simply run ``tmt`` to get started with exploring your working
directory:

.. code-block:: shell

    $ tmt
    Found 2 tests: /tests/docs and /tests/ls.
    Found 3 plans: /plans/basic, /plans/helps and /plans/smoke.
    Found 109 stories: /spec/core/description, /spec/core/order,
    /spec/core/summary, /spec/plans/artifact, /spec/plans/gate,
    /spec/plans/summary, /spec/plans/discover and 103 more.



Init
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before starting a new project initialize the metadata tree root:

.. code-block:: shell

    $ tmt init
    Tree '/tmp/try' initialized.
    To populate it with example content, use --template with mini, base or full.

You can also populate it with a minimal plan example:

.. code-block:: shell

    $ tmt init --template mini
    Tree '/tmp/try' initialized.
    Applying template 'mini'.
    Directory '/tmp/try/plans' created.
    Plan '/tmp/try/plans/example.fmf' created.

Create a plan and a test:

.. code-block:: shell

    $ tmt init --template base
    Tree '/tmp/try' initialized.
    Applying template 'base'.
    Directory '/tmp/try/tests/example' created.
    Test metadata '/tmp/try/tests/example/main.fmf' created.
    Test script '/tmp/try/tests/example/test.sh' created.
    Directory '/tmp/try/plans' created.
    Plan '/tmp/try/plans/example.fmf' created.

Initialize with a richer example that also includes the story
(overwriting existing files):

.. code-block:: shell

    $ tmt init --template full --force
    Tree '/tmp/try' already exists.
    Applying template 'full'.
    Directory '/tmp/try/tests/example' already exists.
    Test metadata '/tmp/try/tests/example/main.fmf' overwritten.
    Test script '/tmp/try/tests/example/test.sh' overwritten.
    Directory '/tmp/try/plans' already exists.
    Plan '/tmp/try/plans/example.fmf' overwritten.
    Directory '/tmp/try/stories' created.
    Story '/tmp/try/stories/example.fmf' created.



Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``tests`` command is used to investigate and handle tests.
See the :ref:`specification` for details about the L1 Metadata.


Explore Tests
------------------------------------------------------------------

Use ``tmt tests`` to briefly list discovered tests:

.. code-block:: shell

    $ tmt tests
    Found 2 tests: /tests/docs and /tests/ls.

Use ``tmt tests ls`` to list available tests, one per line:

.. code-block:: shell

    $ tmt tests ls
    /tests/docs
    /tests/ls

Use ``tmt tests show`` to see detailed test metadata:

.. code-block:: shell

    $ tmt tests show
    /tests/docs
         summary Check that essential documentation is working
         contact Petr Šplíchal <psplicha@redhat.com>
            test ./test.sh
            path /tests/docs
        duration 5m
            tier 0
          result respect
         enabled yes

    /tests/ls
         summary List available tests and plans
     description Make sure that 'tmt test ls' and 'tmt plan ls' work.
         contact Petr Šplíchal <psplicha@redhat.com>
            test ./test.sh
            path /tests/ls
        duration 5m
            tier 1
          result respect
         enabled yes

Append ``--verbose`` to get additional information about test as
the list of source files where metadata are defined and its full id:

.. code-block:: shell

    $ tmt tests show /tests/docs --verbose
    /tests/docs
         summary Check that essential documentation is working
         contact Petr Šplíchal <psplicha@redhat.com>
            test ./test.sh
            path /tests/docs
        duration 5m
            tier 0
          result respect
         enabled yes
         sources /home/psss/git/tmt/tests/main.fmf
                 /home/psss/git/tmt/tests/docs/main.fmf
          fmf-id name: /tests/docs
                 url: https://github.com/teemtee/tmt.git


Filter Tests
------------------------------------------------------------------

Both ``tmt tests ls`` and ``tmt tests show`` can optionally filter
tests with a regular expression, filter expression, a Python
condition or link expression:

.. code-block:: shell

    $ tmt tests show docs
    /tests/docs
         summary Check that essential documentation is working
         contact Petr Šplíchal <psplicha@redhat.com>
            test ./test.sh
            path /tests/docs
        duration 5m
            tier 0
          result respect
         enabled yes

    $ tmt tests ls --filter 'tier: 0'
    /tests/docs

    $ tmt tests ls --condition 'tier and int(tier) > 0'
    /tests/ls

    $ tmt tests ls --link verifies:issues/423$
    /tests/prepare/shell

    $ tmt tests ls unit
    /tests/report/junit
    /tests/unit

    $ tmt tests ls unit --exclude junit
    /tests/unit

In order to select tests under the current working directory use
the single dot notation:

.. code-block:: shell

    $ tmt test show .
    $ tmt run test --name .


Import Tests
------------------------------------------------------------------

Use ``tmt tests import`` to gather old metadata stored in
different sources and convert them into the new ``fmf`` format.
By default ``Makefile`` and ``PURPOSE`` files in the current
directory are inspected plus the ``Nitrate`` and ``Polarion`` test
case management systems are contacted to gather all related
metadata.

In order to fetch data from Nitrate you need to have ``nitrate``
module installed. For each test case found in Nitrate separate fmf
file is created with metadata unique to that case. Common metadata
found in all test cases are stored in ``main.fmf``. You can use
``--no-nitrate`` to disable Nitrate integration, ``--no-makefile``
and ``--no-purpose`` switches to disable the other two metadata
sources.

To read data from Polarion you need to install and setup
``pylero`` library (described in `Export tests`_) and enable it
with the ``--polarion`` flag. You can specify ``--polarion-case-id``
instead of searching by values pulled from other sources and you can specify
``--no-link-polarion`` to not save Polarion links. It reads
summary, description, enabled status, assignee, id, component,
tags and links. If ``id`` is not found in Polarion it's generated
and exported.

Argument ``--polarion-case-id`` can be provided multiple times to import
multiple test cases and it supports setting of test names (seprated by ``:``),
if test name is not provided ``Polarion WorkItem ID`` is used
and lastly when ``--no-link-polarion`` is used ``summary`` is taken as test name.
Examples how to use the import with multiple cases and test names:

.. code-block:: shell

    $ tmt test import --polarion --polarion-case-id TMT-123:smoke_test .
    ...
    Metadata successfully stored into '/path/to/test/smoke_test.fmf'.

    $ tmt test import --polarion --polarion-case-id TMT-123:smoke_test --polarion-case-id TMT-124:base_test .
    ...
    Metadata successfully stored into '/path/to/test/main.fmf'.
    Metadata successfully stored into '/path/to/test/smoke_test.fmf'.
    Metadata successfully stored into '/path/to/test/base_test.fmf'.

    $ tmt test import --polarion --polarion-case-id TMT-123 --polarion-case-id TMT-124 .
    ...
    Metadata successfully stored into '/path/to/test/main.fmf'.
    Metadata successfully stored into '/path/to/test/TMT-123.fmf'.
    Metadata successfully stored into '/path/to/test/TMT-124.fmf'.

Manual test cases can be imported from Nitrate using the
``--manual`` option. Provide either ``--case ID`` or ``--plan ID``
with the Nitrate test case/plan identifier to select which test
case should be imported or which test plan should be checked for
manual test cases. Directory ``Manual`` will be created in the fmf
root directory and manual test cases will be imported there.

Example output of metadata conversion:

.. code-block:: shell

    $ tmt test import
    Checking the '/home/psss/git/tmt/examples/convert' directory.
    Makefile found in '/home/psss/git/tmt/examples/convert/Makefile'.
    task: /tmt/smoke
    summary: Simple smoke test
    test: ./runtest.sh
    contact: Petr Splichal <psplicha@redhat.com>
    component: tmt
    duration: 5m
    require: fmf
    recommend: tmt
    Purpose found in '/home/psss/git/tmt/examples/convert/PURPOSE'.
    description:
    Just run 'tmt --help' to make sure the binary is sane.
    This is really that simple. Nothing more here. Really.
    Nitrate test case found 'TC#0603489'.
    extra-summary: tmt convert test
    contact: Petr Šplíchal <psplicha@redhat.com>
    environment:
    {'TEXT': 'Text with spaces', 'X': '1', 'Y': '2', 'Z': '3'}
    tag: ['NoRHEL4', 'NoRHEL5', 'Tier3']
    tier: 3
    component: tmt
    enabled: True
    adjust:
      - enabled: false
        when: distro ~= rhel-4, rhel-5
        continue: false
      - environment:
            PHASES: novalgrind
        when: arch == s390x
        continue: false
    Metadata successfully stored into '/home/psss/git/tmt/examples/convert/main.fmf'.

And here's the resulting ``main.fmf`` file:

.. code-block:: yaml

    summary: Simple smoke test
    description: |
        Just run 'tmt --help' to make sure the binary is sane.
        This is really that simple. Nothing more here. Really.
    contact: Petr Šplíchal <psplicha@redhat.com>
    component:
    - tmt
    test: ./runtest.sh
    require:
    - fmf
    recommend:
    - tmt
    environment:
        TEXT: Text with spaces
        X: '1'
        Y: '2'
        Z: '3'
    duration: 5m
    enabled: true
    tag:
    - NoRHEL4
    - NoRHEL5
    - Tier3
    tier: '3'
    adjust:
      - enabled: false
        when: distro ~= rhel-4, rhel-5
        continue: false
      - environment:
            PHASES: novalgrind
        when: arch == s390x
        continue: false
    extra-summary: tmt convert test
    extra-task: /tmt/smoke
    extra-nitrate: TC#0603489


Export Tests
------------------------------------------------------------------

Use ``tmt tests export`` command to export test metadata into
different formats and tools. By default all available tests are
exported, specify regular expression matching test name to export
only selected tests or use ``.`` to export tests under the current
directory:

.. code-block:: shell

    $ tmt tests export --how nitrate .
    Test case 'TC#0603489' found.
    summary: tmt convert test
    script: /tmt/smoke
    components: tmt
    tags: NoRHEL4 Tier3 NoRHEL5 fmf-export
    default tester: psplicha@redhat.com
    estimated time: 5m
    status: CONFIRMED
    arguments: TEXT='Text with spaces' X=1 Y=2 Z=3
    Structured Field:
    distro = rhel-6: False
    description: Simple smoke test
    purpose-file: Just run 'tmt --help' to make sure the binary is sane.
    This is really that simple. Nothing more here. Really.
    fmf id:
    name: /
    path: /examples/convert
    url: https://github.com/teemtee/tmt.git
    Test case 'TC#0603489' successfully exported to nitrate.

    $ tmt test export --how polarion --project-id TMT --create .
    Test case 'TMT-42' created.
    title: This is case what already exists inside polarion
    description: tmt /existing_testcase - This is case what already exists inside polarion
    script: https://github.com/teemtee/tmt.git
    components: tmt
    tags: integration fmf-export
    enabled: True
    Append the Polarion test case link.
    implements: https://polarion.example/polarion/#/project/TMT/workitem?id=TMT-42
    Test case 'This is case what already exists inside polarion' successfully exported to Polarion.

Before export to ``--how nitrate`` tmt checks that used test
metadata are committed to git and present on ``origin`` remote.
On own risk the failure can be ignored with ``--ignore-git-validation``.

Nitrate test case can be created from test metadata with ``--create``.
By default existing cases are detected each time, if you need to
create additional nitrate test case use ``--duplicate``.
Export will append ``extra-nitrate`` to the test metadata.
Those changes have to be committed and pushed manually.

To include nitrate test case in general plans use ``--general``.
Set of general plans to which the test case will be linked is
detected from the :ref:`/spec/tests/component`. Any additional
general plan will be removed.

For newly created nitrate test case it can be useful to add it
to all open nitrate test runs under its general plans. This can be
done using the ``--link-runs`` option.

Use the ``--bugzilla`` option together with ``--how nitrate`` or
``--how polarion`` to link bugs marked as ``verifies``
in the :ref:`/spec/core/link` attribute with the corresponding
Nitrate/Polarion test case.

Almost all important attributes should be pulled from fmf metadata
both for Nitrate and Polarion including: Title, Description,
Author, Assignee, Automation, Automation script, Level, Component,
Test type, Tags, Importance, Status, Linked BZs and possibly more
in the future.

Also a unique id generated by tmt (automatically during export) is
added into Notes (Nitrate) or Test Case ID (Polarion) fields for
matching cases across all test case management systems.

Configuration and guide for setting up nitrate can be found
at https://github.com/psss/python-nitrate

Configuration and guide for setting up pylero can be found
at https://github.com/RedHatQE/pylero

Test Libraries
------------------------------------------------------------------

In order to prevent unnecessary test code duplication it makes
sense to use a test library which implements frequently repeated
actions. Currently beakerlib libraries are supported. They can be
defined in the :ref:`/spec/tests/require` attribute and are
fetched during the :ref:`/spec/plans/discover` step.

Use the short backward-compatible syntax to fetch libraries from
the `default repository`__:

.. code-block:: yaml

    require: library(openssl/certgen)

__ https://github.com/beakerlib/

The full fmf identifier allows to fetch libraries from arbitrary
location:

.. code-block:: yaml

    require:
      - url: https://github.com/beakerlib/openssl
        name: /certgen

See the :ref:`/spec/tests/require` attribute specification for
detailed description of the syntax and available keys.



Plans
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``plans`` command is used to investigate and handle plans.
See the :ref:`specification` for details about the L2 Metadata.


Explore Plans
------------------------------------------------------------------

Exploring ``plans`` is similar to using ``tests``:

.. code-block:: shell

    $ tmt plans
    Found 3 plans: /plans/basic, /plans/helps and /plans/smoke.

Use ``tmt plans ls`` and ``tmt plans show`` to output plan names
and detailed plan information, respectively:

.. code-block:: shell

    $ tmt plans ls
    /plans/basic
    /plans/helps
    /plans/smoke

    $ tmt plans show
    /plans/basic
         summary Essential command line features
        discover
             how fmf
      repository https://github.com/teemtee/tmt
        revision devel
          filter tier: 0,1
         prepare
             how ansible
        playbook ansible/packages.yml

    /plans/helps
         summary Check help messages
        discover
             how shell

    /plans/smoke
         summary Just a basic smoke test
         execute
             how shell
          script tmt --help

Verbose output and filtering are similar as for exploring tests.
See `Explore Tests`_ and `Filter Tests`_ for more examples.


.. _multiple-configs:

Multiple Configs
------------------------------------------------------------------

Step can contain multiple configurations. In this case provide
each config with a unique name. Applying ansible playbook and
executing custom script in a single :ref:`/spec/plans/prepare`
step could look like this:

.. code-block:: yaml

    prepare:
      - name: packages
        how: ansible
        playbook: ansible/packages.yml
      - name: services
        how: shell
        script: systemctl start service

Another common use case which can be easily covered by multiple
configs can be fetching tests from multiple repositories during
the :ref:`/spec/plans/discover` step:

.. code-block:: yaml

    discover:
      - name: upstream
        how: fmf
        url: https://github.com/teemtee/tmt
      - name: fedora
        how: fmf
        url: https://src.fedoraproject.org/rpms/tmt/


Extend Steps
------------------------------------------------------------------

When defining multiple configurations for a step it is also
possible to make use of fmf inheritance. For example the common
preparation config can be defined up in the hierarchy:

.. code-block:: yaml

    prepare:
      - name: tmt
        how: install
        package: tmt

Extending the prepare config in a child plan to install additional
package then could be done in the following way:

.. code-block:: yaml

    prepare+:
      - name: pytest
        how: install
        package: python3-pytest

Eventually, use :ref:`/spec/core/adjust` to extend the step
conditionally:

.. code-block:: yaml

    adjust:
      - when: distro == fedora
        prepare+:
          - name: pytest
            how: install
            package: python3-pytest


Parametrize Plans
------------------------------------------------------------------

It is possible to parametrize plans using environment variables and
context. This may be useful to reduce duplication, for example in
CI systems.

For :ref:`/spec/plans/environment` variables the syntax is
standard, both ``$var`` and ``${var}`` may be used. The values of
variables are taken from the ``--environment`` command line option
and the ``environment`` plan attribute. If a variable is defined
using both the attribute and the option, the value from the
``--environment`` option has a priority:

.. code-block:: yaml

    discover:
        how: fmf
        url: https://github.com/teemtee/${REPO}

    $ tmt run -e REPO=tmt

Variables can be also utilized to pick tests from specific discovery phase.
The command line (``tmt run tests --name ...``) applies for the whole discovery
step and would select more tests than required in the case the test names are not unique:

.. code-block:: yaml

    discover:
      - how: fmf
        url: https://github.com/teemtee/tmt.git
        test: ${PICK_TMT}
      - how: fmf
        url: https://github.com/teemtee/fmf.git
        test: ${PICK_FMF}

    $ tmt run -e PICK_TMT='^/tests/core/ls$' -e PICK_FMF='^/tests/(unit|basic/ls)$'

For :ref:`context</spec/context>` parametrization the syntax is
``$@dimension`` or ``$@{dimension}``. The values are set according
to the defined context specified using ``--context`` command line
option and the ``context`` plan attribute:

.. code-block:: yaml

    context:
        branch: main
    discover:
        how: fmf
        url: https://github.com/teemtee/tmt
        ref: $@{branch}

    $ tmt -c branch=tmt run


Dynamic ``ref`` Evaluation
------------------------------------------------------------------

When using test branching for test maintenance it becomes handy to
be able to set ``ref`` dynamically depending on the provided
:ref:`/spec/context`. This is possible using a special file in tmt format
stored in a default branch of a tests repository. That special file
should contain rules assigning attribute ``ref`` in an ``adjust``
block depending on the context.

Dynamic ``ref`` assignment is enabled whenever a test plan reference
has the format ``ref: @FILEPATH``.

Example of a test plan:

.. code-block:: yaml

    discover:
        how: fmf
        url: https://github.com/teemtee/repo
        ref: "@.tmtref"

Example of a dynamic ``ref`` definition file in ``repo/.tmtref``:

.. code-block:: yaml

    ref: main
    adjust:
      - when: distro == centos-stream-9
        ref: rhel-9
      - when: distro == fedora
        ref: fedora
      - when: distro == rhel-9
        ref: rhel-9

The definition file can also be parametrized using environment
variables or context dimensions:

.. code-block:: yaml

    ref: main
    adjust:
      - when: distro == fedora or distro == rhel
        ref: $@distro


Stories
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``stories`` command is used to investigate and handle stories.
See the :ref:`specification` for details about the L3 Metadata.


Explore Stories
------------------------------------------------------------------

Exploring ``stories`` is quite similar to using ``tests`` or
``plans``:

.. code-block:: shell

    $ tmt stories
    Found 109 stories: /spec/core/description, /spec/core/order,
    /spec/core/summary, /spec/plans/artifact, /spec/plans/gate,
    /spec/plans/summary, /spec/plans/discover and 102 more.

The ``tmt stories ls`` and ``tmt stories show`` commands output
the names and the detailed information, respectively:

.. code-block:: shell

    $ tmt stories ls
    /spec/core/description
    /spec/core/order
    /spec/core/summary
    ...

    $ tmt stories show
    /spec/core/description
         summary Detailed description of the object
           story I want to have common core attributes used consistently
                 across all metadata levels.
     description Multiline ``string`` describing all important aspects of
                 the object. Usually spans across several paragraphs. For
                 detailed examples using a dedicated attributes 'examples'
                 should be considered.
     ...

Verbose output and filtering are similar as for exploring tests.
See `Explore Tests`_ and `Filter Tests`_ for more examples.


Filter Stories
------------------------------------------------------------------

Additionally, and specifically to stories, special flags are
available for binary status filtering:

.. code-block:: shell

    $ tmt stories show --help | grep only
      -i, --implemented    Implemented stories only.
      -I, --unimplemented  Unimplemented stories only.
      -t, --verified       Stories verified by tests.
      -T, --unverified     Stories not verified by tests.
      -d, --documented     Documented stories only.
      -D, --undocumented   Undocumented stories only.
      -c, --covered        Covered stories only.
      -C, --uncovered      Uncovered stories only.

    $ tmt stories ls --implemented
    /spec/core/summary
    /stories/api/plan/attributes/artifact
    /stories/api/plan/attributes/gate
    ...

    $ tmt stories show --documented
    /stories/cli/common/debug
         summary Print out everything tmt is doing
           story I want to have common command line options consistenly used
                 across all supported commands and subcommands.
         example tmt run -d
                 tmt run --debug
     implemented /tmt/cli
      documented /tmt/cli
    ...

In order to select stories under the current working directory use
the single dot notation:

.. code-block:: shell

    $ tmt story show .


Story Coverage
------------------------------------------------------------------

Current status of the code, test and documentation coverage can be
checked using the ``tmt story coverage`` command:

.. code-block:: shell

    $ tmt story coverage
    code test docs story
    todo todo todo /spec/core/description
    todo todo todo /spec/core/order
    done todo todo /spec/core/summary
    ...
    done todo todo /stories/cli/usability/completion
     39%   9%   9% from 109 stories


Run
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``tmt run`` command is used to execute tests. By default all
steps for all discovered test plans are executed:

.. code-block:: shell

    $ tmt run
    /var/tmp/tmt/run-581

    /plans/basic
        discover
            how: fmf
            directory: /home/psss/git/tmt
            filter: tier: 0,1,2
            summary: 15 tests selected
        provision
            how: local
            distro: Fedora release 32 (Thirty Two)
            summary: 1 guest provisioned
        prepare
            how: ansible
            playbook: ansible/packages.yml
            how: install
            summary: Install required packages
            package: beakerlib
            summary: 2 preparations applied
        execute
            how: tmt
            summary: 15 tests executed
        report
            how: display
            summary: 15 tests passed
        finish
            summary: 0 tasks completed

Even if there are no :ref:`/spec/plans` defined it is still
possible to execute tests and custom scripts. See the default
:ref:`/stories/cli/run/default/plan` story for details.

Dry run mode is enabled with the ``--dry`` option:

.. code-block:: shell

    tmt run --dry

Each test run creates a workdir where relevant data such as tests
code from the discover step or test results from the execute step
are stored. If you don't need to investigate test logs and other
artifacts generated by the run you can remove the workdir after
the execution is finished:

.. code-block:: shell

    tmt run --remove
    tmt run --rm
    tmt run -r


Select Plans
------------------------------------------------------------------

Choose which plans should be executed:

.. code-block:: shell

    $ tmt run plan --name basic
    /var/tmp/tmt/run-083

    /plans/basic
        discover
            how: fmf
            url: https://github.com/teemtee/tmt
            ref: devel
            filter: tier: 0,1
            tests: 2 tests selected
        provision
        prepare
        execute
            how: tmt
            result: 2 tests passed, 0 tests failed
        report
        finish


Select Tests
------------------------------------------------------------------

Run only a subset of available tests across all plans:

.. code-block:: shell

    $ tmt run test --filter tier:1
    /plans/basic
        discover
            how: fmf
            url: https://github.com/teemtee/tmt
            ref: devel
            filter: tier: 0,1
            tests: 1 test selected
        ...

    /plans/helps
        discover
            how: shell
            directory: /home/psss/git/tmt
            tests: 0 tests selected
        ...

    /plans/smoke
        discover
            how: shell
            tests: 0 tests selected
        ...

To run only tests defined in the current working directory:

.. code-block:: shell

    $ tmt run test --name .

Select Steps
------------------------------------------------------------------

The test execution is divided into the following six steps:
``discover``, ``provision``, ``prepare``, ``execute``, ``report``
and ``finish``. See the :ref:`specification` for more details
about individual steps.

It is possible to execute only selected steps. For example in
order to see which tests would be executed without actually
running them choose the ``discover`` step:

.. code-block:: shell

    $ tmt run discover
    /var/tmp/tmt/run-085

    /plans/basic
        discover
            how: fmf
            url: https://github.com/teemtee/tmt
            ref: devel
            filter: tier: 0,1
            tests: 2 tests selected

    /plans/helps
        discover
            how: shell
            directory: /home/psss/git/tmt
            tests: 4 tests selected

Use ``--verbose`` and ``--debug`` to enable more detailed output
such as list of individual tests or showing the progress of the
test environment provisioning:

.. code-block:: shell

    $ tmt run discover --verbose
    /var/tmp/tmt/run-767

    /plans/basic
        discover
            how: fmf
            url: https://github.com/teemtee/tmt
            ref: devel
            filter: tier: 0,1
            tests: 2 tests selected
                /one/tests/docs
                /one/tests/ls

    /plans/helps
        discover
            how: shell
            directory: /home/psss/git/tmt
            tests: 4 tests selected
                /help/main
                /help/test
                /help/plan
                /help/smoke

You can also choose multiple steps to be executed:

.. code-block:: shell

    tmt run discover provision prepare

Arguments for particular step can be specified after the step
name, options for all steps should go to the ``run`` command:

.. code-block:: shell

    # debug output for provision only
    tmt run discover provision --debug

    # debug output for all steps
    tmt run --debug discover provision

In order to execute all test steps while providing arguments to
some of them it is possible to use the ``--all`` option:

.. code-block:: shell

    tmt run --all provision --how=local


Execute Progress
------------------------------------------------------------------

When run in terminal ``execute`` step prints name of the executed test
unless ``--debug`` or ``--verbose`` options are used:

.. code-block:: shell

    $ tmt run

        execute
            how: tmt
            progress: /tests/core/enabled [5/16]


In the verbose mode the duration and result after the test is executed
are printed:

.. code-block:: shell

    $ tmt run --all execute -v

        execute
            how: tmt
                00:00:03 pass /tests/core/adjust [1/16]

More verbose mode prints summary of the test being executed first:

.. code-block:: shell

    $ tmt run --all execute -vv

        execute
            how: tmt
            exit-first: False
                test: Verify test/plan adjustments based on context
                    00:00:04 pass /tests/core/adjust [1/16]

The most verbose mode prints also the test output:

.. code-block:: shell

    $ tmt run --all execute -vvv

        execute
            how: tmt
            order: 50
            exit-first: False
                test: Verify test/plan adjustments based on context
                    out:
                    out: ::::::::::::::::::::::::::::::::::::::::::::
                    out: ::   Setup
                    out: ::::::::::::::::::::::::::::::::::::::::::::
                    out:
                    out: :: [ 17:03:06 ] :: [  BEGIN   ] :: Create...
                        ....
                    00:00:04 pass /tests/core/adjust [1/16]


Check Report
------------------------------------------------------------------

When a particular step is ``done``, it won't be executed
repeatedly unless ``--force`` is used:

.. code-block:: shell

    $ tmt run -l report --verbose
    /plans/features/core
        report
            status: done
            summary: 10 tests passed

If you need additional information about your already ``done``
run use ``--force`` together with the ``--verbose`` option:

.. code-block:: shell

    $ tmt run -l report -v --force
    /plans/features/core
        report
            how: display
                pass /tests/core/adjust
                pass /tests/core/docs
                pass /tests/core/dry
                pass /tests/core/env
                pass /tests/core/error
                pass /tests/core/force
                pass /tests/core/ls
                pass /tests/core/path
                pass /tests/core/smoke
                pass /tests/unit
            summary: 10 tests passed

In order to investigate test logs raise verbosity even more:

.. code-block:: shell

    $ tmt run -l report -vv --force
    /plans/features/core
        report
            how: display
                pass /tests/core/adjust
                    output.txt: /var/tmp/tmt/run-759/plans/features/core/execute/data/tests/core/adjust/output.txt
                    journal.txt: /var/tmp/tmt/run-759/plans/features/core/execute/data/tests/core/adjust/journal.txt
                pass /tests/core/docs
                    output.txt: /var/tmp/tmt/run-759/plans/features/core/execute/data/tests/core/docs/output.txt
                    journal.txt: /var/tmp/tmt/run-759/plans/features/core/execute/data/tests/core/docs/journal.txt
                pass /tests/core/dry
                    output.txt: /var/tmp/tmt/run-759/plans/features/core/execute/data/tests/core/dry/output.txt
                    journal.txt: /var/tmp/tmt/run-759/plans/features/core/execute/data/tests/core/dry/journal.txt
                ...
            summary: 10 tests passed

Use level 3 verbosity ``-vvv`` to show the complete test output.
For more comfortable review, generate an ``html`` report and open
it in your favorite web browser:

.. code-block:: shell

    $ tmt run --last report --how html --open --force
    $ tmt run -l report -h html -of


Provision Options
------------------------------------------------------------------

By default, tests are executed under a virtual machine so that
your laptop is not affected by unexpected changes. The following
commands are equivalent:

.. code-block:: shell

    tmt run
    tmt run -a provision -h virtual
    tmt run --all provision --how=virtual

You can also use an alternative virtual machine implementation
using the ``testcloud`` provisioner:

.. code-block:: shell

    tmt run --all provision --how=virtual.testcloud

If you already have a box ready for testing with ``ssh`` enabled,
use the ``connect`` method:

.. code-block:: shell

    tmt run --all provision --how=connect --guest=name-or-ip --user=login --password=secret
    tmt run --all provision --how=connect --guest=name-or-ip --key=private-key-path

The ``container`` method allows to execute tests in a container
using ``podman``:

.. code-block:: shell

    tmt run --all provision --how=container --image=fedora:latest

If you are confident that tests are safe you can execute them
directly on your ``local`` host:

.. code-block:: shell

    tmt run --all provision --how=local

In order to reboot a provisioned guest use the ``reboot`` command.
By default a soft reboot is performed which should prevent data
loss, use ``--hard`` to force a hard reboot:

.. code-block:: shell

    tmt run --last reboot
    tmt run --last reboot --hard


Debug Tests
------------------------------------------------------------------

Sometimes the environment preparation can take a long time. Thus,
especially for debugging tests, it usually makes sense to run the
``provision`` and ``prepare`` step only once, then ``execute``
tests as many times as necessary to debug the test code and
finally clean up when debugging is done:

.. code-block:: shell

    tmt run --id <ID> --until execute    # prepare, run test once

    tmt run -i <ID> execute -f           # run test again
    tmt run -i <ID> execute -f           # run it again
    tmt run -i <ID> execute -f           # and again

    tmt run -i <ID> report finish

Instead of always specifying the whole run id you can also use
``--last`` or ``-l`` as an abbreviation for the last run id:

.. code-block:: shell

    tmt run --last execute --force
    tmt run -l execute -f

The ``--force`` option instructs ``tmt`` to run given step even if
it has been already completed before. Use ``discover --force`` to
synchronize test code changes to the run workdir:

.. code-block:: shell

    tmt run -l discover -f execute -f

In order to interactively debug tests use the ``--interactive``
option which disables output capturing so that you can see what
exactly is happening during test execution. This also allows to
inspect particular place of the code by inserting a ``bash`` in
the shell code or ``import pdb; pdb.set_trace()`` for python:

.. code-block:: shell

    tmt run --all execute --how tmt --interactive


Aliases
------------------------------------------------------------------

It might be useful to set up a set of shell aliases for the tmt
command lines which you often use. For a quick reservation of
a machine or a container for quick experimenting:

.. code-block:: shell

    alias reserve='tmt run login --step execute execute finish provision --how container --image fedora'

Reserving a testing box then can be as short as this:

.. code-block:: shell

    reserve
    reserve -h virtual
    reserve -i fedora:32
    reserve --how virtual
    reserve --image fedora:32

For interactive debugging of tests the following three aliases can
come in handy:

.. code-block:: shell

    alias start='tmt run --verbose --until report execute --how tmt --interactive test --name . provision --how virtual --image fedora'
    alias retest='tmt run --last test --name . discover -f execute -f --how tmt --interactive'
    alias stop='tmt run --last report --verbose finish'

The test debugging session then can look like this:

.. code-block:: shell

    start
    retest
    retest
    retest login
    ...
    stop

First you ``start`` the session in order to provision a testing
environment, then you ``retest`` your test code changes as many
times as you need to finalize the test implementation, and finally
``stop`` is used to clean up the testing environment.


Guest Login
------------------------------------------------------------------

Use the ``login`` command to get an interactive shell on the
provisined guest. This can be useful for example for additional
manual preparation of the guest before testing or checking test
logs to investigate a test failure:

.. code-block:: shell

    tmt run login --step prepare
    tmt run login --step execute

It's possible to log in at the start or end of a step or select
the desired step phase using order:

.. code-block:: shell

    tmt run login --step prepare:start
    tmt run login --step prepare:50
    tmt run login --step prepare:end

Interactive shell session can be also enabled conditionally when
specific test result occurs:

.. code-block:: shell

    tmt run login --when fail
    tmt run login --when fail --when error

You can also enable only the ``provision`` step to easily get a
clean and safe environment for experimenting. Use the ``finish``
step to remove provisioned guest:

.. code-block:: shell

    tmt run provision login
    tmt run --last finish

Clean up the box right after your are done with experimenting by
combining the above-mentioned commands on a single line:

.. code-block:: shell

    tmt run provision login finish

Login can be used to run an arbitrary script on a provisioned
guest. This can be handy if you want to run arbitrary scripts between
steps for example. This is currently used in the Testing Farm's
`tmt reproducer`__:

.. code-block:: shell

    tmt run --last login < script.sh

__ https://docs.testing-farm.io/general/0.1/test-results.html#_tmt_reproducer

Have you heard already that using command abbreviation is possible
as well? It might save you some typing:

.. code-block:: shell

    tmt run pro log fin

See the :ref:`/stories/cli/run/login` user stories for more
details and examples.



Status
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``status`` command is used to inspect the progress of runs,
plans and steps that have previously been started:

.. code-block:: shell

    $ tmt status
    status     id
    prepare    /var/tmp/tmt/run-002
    done       /var/tmp/tmt/run-001


Verbosity Levels
------------------------------------------------------------------

With no verbosity (the default), the status of whole runs is
displayed as shown above. The last done step is shown as the run
status (or 'done' if all enabled steps are completed). With more
verbosity (-v), the status of plans in runs is shown:

.. code-block:: shell

    $ tmt status -v
    status     id
    prepare    /var/tmp/tmt/run-002  /base
    done       /var/tmp/tmt/run-001  /advanced
    done       /var/tmp/tmt/run-001  /base

With the highest verbosity (-vv), the status of individual steps
for each plan is displayed:

.. code-block:: shell

    $ tmt status -vv
    disc prov prep exec repo fini  id
    done done done todo todo todo  /var/tmp/tmt/run-002  /base
    done done done done todo done  /var/tmp/tmt/run-001  /advanced
    done done done done todo done  /var/tmp/tmt/run-001  /base


Status Filtering
------------------------------------------------------------------

The runs shown in the status are by default taken from
``/var/tmp/tmt``. The directory containing runs can be specified
using an argument to ``tmt status``:

.. code-block:: shell

    $ tmt status /tmp/run
    status     id
    done       /tmp/run/001

Status of one specific run can also be shown using the ``--id``
option:

.. code-block:: shell

    $ tmt status -vv --id run-002
    disc prov prep exec repo fini  id
    done done done todo todo todo  /var/tmp/tmt/run-002  /base

Runs and plans can also be filtered based on their status. Option
``--abandoned`` can be used to list runs/plans which have
provision step completed but finish step not yet done. This is
useful for finding active containers or virtual machines:

.. code-block:: shell

    $ tmt status --abandoned
    status     id
    prepare    /var/tmp/tmt/run-002

To show only completed runs/plans, ``--finished`` can be used:

.. code-block:: shell

    $ tmt status --finished
    status     id
    done       /var/tmp/tmt/run-001

Finally, ``--active`` displays runs/plans in progress (at least
one enabled step has not been finished):

.. code-block:: shell

    $ tmt status --active
    status     id
    prepare    /var/tmp/tmt/run-002



Clean
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When running tests, a lot of metadata can gather over time taking
a lot of space. It may be useful to clean it every now and then
using the ``clean`` command. Its goal is to stop the running
guests, remove working directories or remove images. Without any
subcommand, all of these actions are done:

.. code-block:: shell

    $ tmt clean
    clean
        guests
        runs
        images
            testcloud

It may be useful to see exactly which runs are affected using
the ``--verbose`` option:

.. code-block:: shell

    $ tmt clean -v
    clean
        guests
            Stopping guests in run '/var/tmp/tmt/run-001' plan '/base'.
        runs
            Removing workdir '/var/tmp/tmt/run-003'.
            Removing workdir '/var/tmp/tmt/run-002'.
            Removing workdir '/var/tmp/tmt/run-001'.
        images
            testcloud
                warn: Directory '/var/tmp/tmt/testcloud/images' does not exist.

However, before cleaning up all available metadata, you may want
to see what would actually happen using ``--dry`` mode:

.. code-block:: shell

    $ tmt clean -v --dry
    clean
        guests
            Would stop guests in run '/var/tmp/tmt/run-001' plan '/advanced'.
            Would stop guests in run '/var/tmp/tmt/run-001' plan '/base'.
        runs
            Would remove workdir '/var/tmp/tmt/run-002'.
            Would remove workdir '/var/tmp/tmt/run-001'.
        images
            testcloud
                warn: Directory '/var/tmp/tmt/testcloud/images' does not exist.

In some cases, you may want to have a bit more control over the
behaviour which can be achieved using subcommands and their
options. All of the options described above can be used with
individual subcommands too.


Clean guests
------------------------------------------------------------------

The subcommand ``clean guests`` aims to stop all running guests.
By default, runs are taken from ``/var/tmp/tmt``, this can be
changed using an argument to the subcommand:

.. code-block:: shell

    $ tmt clean guests -v /tmp/run
    clean
        guests
            Stopping guests in run '/tmp/run/002' plan '/advanced'.
            Stopping guests in run '/tmp/run/002' plan '/base'.

You may also want to clean the guests in only one run using
``--id`` or ``--last`` options. This serves as an alternative
to ``tmt run --last finish``:

.. code-block:: shell

    $ tmt clean guests -v --last
    clean
        guests
            Stopping guests in run '/var/tmp/tmt/run-003' plan '/advanced'.
            Stopping guests in run '/var/tmp/tmt/run-003' plan '/base'.

The type of provision to be cleaned can be changed using
``--how`` option:

.. code-block:: shell

    $ tmt run provision -h container
    /var/tmp/tmt/run-001
    ...

    $ tmt run provision -h virtual
    /var/tmp/tmt/run-002
    ...

    $ tmt clean guests --how container
    clean
        guests
            Stopping guests in run '/var/tmp/tmt/run-001' plan '/advanced'.
            Stopping guests in run '/var/tmp/tmt/run-001' plan '/base'.

    $ tmt clean guests --how virtual
    clean
        guests
            Stopping guests in run '/var/tmp/tmt/run-002' plan '/advanced'.
            Stopping guests in run '/var/tmp/tmt/run-002' plan '/base'.


Clean workdirs
------------------------------------------------------------------

The goal of ``clean runs`` is to remove workdirs of past runs.
Similarly to above, ``/var/tmp/tmt`` is used by default as run
location and this can be changed using an argument:

.. code-block:: shell

    $ tmt clean runs /tmp/run
    clean
        runs
            Removing workdir '/tmp/run/001'.

Only one specific run can also be removed using ``--id`` or
``--last`` options, similarly to ``clean guests``:

.. code-block:: shell

    $ tmt clean runs -v -i /var/tmp/tmt/run-001
    clean
        runs
            Removing workdir '/var/tmp/tmt/run-001'.

You may also want to remove only old runs. This can be achieved
using ``--keep`` option which allows you to specify the number
of latest runs to keep:

.. code-block:: shell

    $ for i in $(seq 1 10); do tmt run; done
    ...

    $ tmt clean runs --dry -v --keep 5
    clean
        runs
            Would remove workdir '/var/tmp/tmt/run-005'.
            Would remove workdir '/var/tmp/tmt/run-004'.
            Would remove workdir '/var/tmp/tmt/run-003'.
            Would remove workdir '/var/tmp/tmt/run-002'.
            Would remove workdir '/var/tmp/tmt/run-001'.


Clean images
------------------------------------------------------------------

The subcommand ``clean images`` removes images of all provision
methods that support it. Currently, only testcloud provision
supports this option, the images are removed from
``/var/tmp/tmt/testcloud/images``:

.. code-block:: shell

    $ tmt clean images
    clean
        images
            testcloud
                Removing '/var/tmp/tmt/testcloud/images/Fedora-Cloud-Base-34_Beta-1.3.x86_64.qcow2'.


Coding
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to perform more advanced processing of the metadata
which is not supported by the command line use Python. To get
quickly started just import the ``tmt`` module and grow a new
``tmt.Tree`` object:

.. code-block:: python

    import tmt

    tree = tmt.Tree.grow()

    for test in tree.tests():
        print(test.name)

Use the ``tmt.utils.Path`` class when specifying paths:

.. code-block:: python

    from tmt.utils import Path

    tree = tmt.Tree.grow(path=Path("/path/to/the/tree"))
