.. _examples:

======================
    Examples
======================

Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
multiple test cases and it supports setting of test names (separated by ``:``),
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
detected from the :tmt:story:`/spec/tests/component`. Any additional
general plan will be removed.

For newly created nitrate test case it can be useful to add it
to all open nitrate test runs under its general plans. This can be
done using the ``--link-runs`` option.

Use the ``--bugzilla`` option together with ``--how nitrate`` or
``--how polarion`` to link bugs marked as ``verifies``
in the :tmt:story:`/spec/core/link` attribute with the corresponding
Nitrate/Polarion test case.

Almost all important attributes should be pulled from fmf metadata
both for Nitrate and Polarion including: Title, Description,
Author, Assignee, Automation, Automation script, Level, Component,
Test type, Tags, Importance, Status, Linked BZs and possibly more
in the future.

Also a unique id generated by tmt (automatically during export) is
added into Notes (Nitrate) or tmt ID (Polarion) fields for
matching cases across all test case management systems.

Configuration and guide for setting up nitrate can be found
at https://github.com/psss/python-nitrate

Configuration and guide for setting up pylero can be found
at https://github.com/RedHatQE/pylero


BeakerLib Libraries
------------------------------------------------------------------

In order to prevent unnecessary test code duplication it makes
sense to use a test library which implements frequently repeated
actions. Currently beakerlib libraries are supported. They can be
defined in the :tmt:story:`/spec/tests/require` attribute and are
fetched during the :tmt:story:`/spec/plans/discover` step.

Use the short backward-compatible syntax to fetch libraries from
the `default repository`__:

.. code-block:: yaml

    require: library(openssl/certgen)

__ https://github.com/beakerlib/

The full fmf identifier allows to fetch libraries from arbitrary
location:

.. code-block:: yaml

    require:
      - type: library
        url: https://github.com/beakerlib/openssl
        name: /certgen

See the :tmt:story:`/spec/tests/require` attribute specification for
detailed description of the syntax and available keys.



Plans
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Parametrize Plans
------------------------------------------------------------------

It is possible to parametrize plans using environment variables and
context. This may be useful to reduce duplication, for example in
CI systems.

For :tmt:story:`/spec/plans/environment` variables the syntax is
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

For :tmt:story:`context</spec/context>` parametrization the syntax is
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
be able to set :ref:`ref</plugins/discover/fmf>` dynamically
depending on the provided :tmt:story:`/spec/context`. This is possible
using a special file in tmt format stored in a default branch of a
tests repository. That special file should contain rules assigning
attribute ``ref`` in an ``adjust`` block depending on the context.

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
