.. _guide:

======================
    Guide
======================

This guide will show you the way through the dense forest of
available ``tmt`` features, commands and options. But don't be
afraid, we will start slowly, with the simple examples first. And
then, when your eyes get accustomed to the shadow of omni-present
metadata `trees`__, we will slowly dive deeper and deeper so that
you don't miss any essential functionality which could make your
life smarter, brighter and more joyful. Let's go, follow me...

__ https://fmf.readthedocs.io/en/stable/concept.html#trees


The First Steps
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Installing the main package with the core functionality is quite
straightforward. No worry, there are just a few dependencies:

.. code-block:: shell

    sudo dnf install -y tmt

Enabling a simple smoke test in the continuous integration should
be a joy. Just a couple of concise commands, assuming you are in
your project git repository:

.. code-block:: shell

    tmt init --template mini
    vim plans/example.fmf

Open the example plan in your favorite editor and adjust the smoke
test script as needed. Your very first plan can look like this:

.. code-block:: yaml

    summary: Basic smoke test
    execute:
        script: foo --version

Now you're ready to create a new pull request to check out how
it's working. During push, remote usually shows a direct link to
the page with a *Create* button, so now it's only two clicks
away:

.. code-block:: shell

    git add .
    git checkout -b smoke-test
    git commit -m "Enable a simple smoke test"
    git push origin -u smoke-test

But perhaps, you are a little bit impatient and would like to see
the results faster. Sure, let's try the smoke test here and now,
directly on your localhost:

.. code-block:: shell

    tmt run --all provision --how local

If you're a bit afraid that the test could break your machine or
just want to keep your environment clean, run it in a container
instead:

.. code-block:: shell

    sudo dnf install -y tmt-provision-container
    tmt run -a provision -h container

Or even in a full virtual machine if the container environment is
not enough. We'll use the :ref:`libvirt<libvirt>` to start a new
virtual machine on your localhost. Be ready for a bit more
dependencies here:

.. code-block:: shell

    sudo dnf install -y tmt-provision-virtual
    tmt run -a provision -h virtual

Don't care about the disk space? Simply install ``tmt-all`` and
you'll get all available functionality at hand. Check the help to
list all supported provision methods:

.. code-block:: shell

    sudo dnf install tmt-all
    tmt run provision --help

Now when you've met your ``--help`` friend you know everything you
need to get around without getting lost in the forest of available
options:

.. code-block:: shell

    tmt --help
    tmt run --help
    tmt run provision --help
    tmt run provision --how container --help

Go on and explore. Don't be shy and ask, ``--help`` is eager to
answer all your questions ;-)


Under The Hood
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Now let's have a brief look under the hood. For storing all config
data we're using the `Flexible Metadata Format`__. In short, it is
a ``yaml`` format extended with a couple of nice features like
`inheritance`__ or virtual `hierarchy`__ which help to maintain
even large data efficiently without unnecessary duplication.

.. _tree:

Trees
------------------------------------------------------------------

The data are organized into `trees`__. Similarly as with ``git``,
there is a special ``.fmf`` directory which marks the root of the
fmf metadata tree. Use the ``init`` command to initialize it:

.. code-block:: shell

    tmt init

Do not forget to include this special ``.fmf`` directory in your
commits, it is essential for building the fmf tree structure which
is created from all ``*.fmf`` files discovered under the fmf root.

__ https://fmf.readthedocs.io
__ https://fmf.readthedocs.io/en/stable/features.html#inheritance
__ https://fmf.readthedocs.io/en/stable/features.html#hierarchy
__ https://fmf.readthedocs.io/en/stable/concept.html#trees


Plans
------------------------------------------------------------------

As we've seen above, in order to enable testing the following plan
is just enough:

.. code-block:: yaml

    execute:
        script: foo --version

Store these two lines in a ``*.fmf`` file and that's it. Name and
location of the file is completely up to you, plans are recognized
by the ``execute`` key which is required. Once the newly created
plan is submitted to the CI system test script will be executed.

By the way, there are several basic templates available which can
be applied already during the ``init`` by using the ``--template``
option or the short version ``-t``. The minimal template, which
includes just a simple plan skeleton, is the fastest way to get
started:

.. code-block:: shell

    tmt init -t mini

:ref:`/spec/plans` are used to enable testing and group relevant
tests together. They describe how to :ref:`/spec/plans/discover`
tests for execution, how to :ref:`/spec/plans/provision` the
environment, how to :ref:`/spec/plans/prepare` it for testing, how
to :ref:`/spec/plans/execute` tests, :ref:`/spec/plans/report`
results and finally how to :ref:`/spec/plans/finish` the test job.

Here's an example of a slightly more complex plan which changes
the default provision method to container to speed up the testing
process and ensures that an additional package is installed before
the testing starts:

.. code-block:: yaml

    provision:
        how: container
        image: fedora:33
    prepare:
        how: install
        package: wget
    execute:
        how: tmt
        script: wget http://example.org/

Note that each of the steps above uses the ``how`` keyword to
choose the desired method which should be applied. Steps can
provide multiple implementations which enables you to choose the
best one for your use case. For example to prepare the guest it's
possible to use the :ref:`/spec/plans/prepare/install` method for
simple package installations, :ref:`/spec/plans/prepare/ansible`
for more complex system setup or :ref:`/spec/plans/prepare/shell`
for arbitrary shell commands.


Tests
------------------------------------------------------------------

Very often testing is much more complex than running just a
single shell script. There might be many scenarios covered by
individual scripts. For these cases the ``discover`` step can
be instructed to explore available tests from fmf metadata as
well. The plan will look like this:

.. code-block:: yaml

    discover:
        how: fmf
    execute:
        how: tmt

:ref:`/spec/tests`, identified by the required key ``test``,
define attributes which are closely related to individual test
cases such as the :ref:`/spec/tests/test` script,
:ref:`/spec/tests/framework`, directory :ref:`/spec/tests/path`
where the test should be executed, maximum test
:ref:`/spec/tests/duration` or packages
:ref:`required</spec/tests/require>` to run the test. Here's an
example of test metadata:

.. code-block:: yaml

    summary: Fetch an example web page
    test: wget http://example.org/
    require: wget
    duration: 1m

Instead of writing the plan and test metadata manualy, you might
want to simply apply the ``base`` template which contains the plan
mentioned above together with a test example including both test
metadata and test script skeleton for inspiration:

.. code-block:: shell

    tmt init --template base

Similar to plans, it is possible to choose an arbitrary name for
the test. Just make sure the ``test`` key is defined. However, to
organize the metadata efficiently it is recommended to keep tests
and plans under separate folders, e.g. ``tests`` and ``plans``.
This will also allow you to use `inheritance`__ to prevent
unnecessary data duplication.

__ https://fmf.readthedocs.io/en/latest/features.html#inheritance


Stories
------------------------------------------------------------------

It's always good to start with a "why". Or, even better, with a
story which can describe more context behind the motivation.
:ref:`/spec/stories` can be used to track implementation, test and
documentation coverage for individual features or requirements.
Thanks to this you can track everything in one place, including
the project implementation progress. Stories are identified by the
``story`` attribute which every story has to define or inherit.

An example story can look like this:

.. code-block:: yaml

    story:
        As a user I want to see more detailed information for
        particular command.
    example:
      - tmt test show -v
      - tmt test show -vvv
      - tmt test show --verbose

In order to start experimenting with the complete set of examples
covering all metadata levels, use the ``full`` template which
creates a test, a plan and a story:

.. code-block:: shell

    tmt init -t full


Core
------------------------------------------------------------------

Finally, there are certain metadata keys which can be used across
all levels. :ref:`/spec/core` attributes cover general metadata
such as :ref:`/spec/core/summary` or :ref:`/spec/core/description`
for describing the content, the :ref:`/spec/core/enabled`
attribute for disabling and enabling tests, plans and stories and
the :ref:`/spec/core/link` key which can be used for tracking
relations between objects.

Here's how the story above could be extended with the core
attributes ``description`` and ``link``:

.. code-block:: yaml

    description:
        Different verbose levels can be enabled by using the
        option several times.
    link:
      - implemented-by: /tmt/cli.py
      - documented-by: /tmt/cli.py
      - verified-by: /tests/core/dry

Last but not least, the core attribute :ref:`/spec/core/adjust`
provides a flexible way to adjust metadata based on the
:ref:`/spec/context`. But this is rather a large topic, so let's
keep it for another time.


Organize Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In the previous chapter we've learned what :ref:`/spec/tests`,
:ref:`/spec/plans` and :ref:`/spec/stories` are used for. Now the
time has come to learn how to efficiently organize them in your
repository. First we'll describe how to easily :ref:`create` new
tests, plans and stories, how to use :ref:`lint` to verify that
all metadata have correct syntax. Finally, we'll dive into
:ref:`inheritance` and :ref:`elasticity` which can substantially
help you to minimize data duplication.

.. _create:

Create
------------------------------------------------------------------

When working on the test coverage, one of the most common actions
is creating new tests. Use ``tmt test create`` to simply create a
new test based on a template:

.. code-block:: shell

    $ tmt test create /tests/smoke
    Template (shell or beakerlib): shell
    Directory '/home/psss/git/tmt/tests/smoke' created.
    Test metadata '/home/psss/git/tmt/tests/smoke/main.fmf' created.
    Test script '/home/psss/git/tmt/tests/smoke/test.sh' created.

As for now there are two templates available, ``shell`` for simple
scripts written in shell and ``beakerlib`` with a basic skeleton
demonstrating essential functions of this shell-level testing
framework. If you want to be faster, specify the desired template
directly on the command line using ``-t`` or ``--template``:

.. code-block:: shell

    $ tmt test create --template shell /tests/smoke
    $ tmt test create --t beakerlib /tests/smoke

In a similar way, the ``tmt plan create`` command can be used to
create a new plan with templates:

.. code-block:: shell

    tmt plans create --template mini /plans/smoke
    tmt plans create --t full /plans/features

When creating many plans, for example when migrating the whole
test coverage from a different tooling, it might be handy to
override default template content directly from the command line.
For this use individual step options such as ``--discover`` and
provide desired data in the ``yaml`` format:

.. code-block:: shell

    tmt plan create /plans/custom --template mini \
        --discover '{how: "fmf", name: "internal", url: "https://internal/repo"}' \
        --discover '{how: "fmf", name: "external", url: "https://external/repo"}'

Now it will be no surprise for you that for creating a new story
the ``tmt story create`` command can be used with the very same
possibility to choose the right template:

.. code-block:: shell

    tmt story create --template full /stories/usability

Sometimes you forget something, or just things may go wrong and
you need another try. In such case add ``-f`` or ``--force`` to
quickly overwrite existing files with the right content.

.. _lint:

Lint
------------------------------------------------------------------

It is easy to introduce a syntax error to one of the fmf files and
make the whole tree broken. The ``tmt lint`` command performs a
set of :ref:`lint-checks` which compare the stored metadata
against the specification and reports anything suspicious:

.. code-block:: shell

    $ tmt lint /tests/execute/basic
    /tests/execute/basic
    pass C000 fmf node passes schema validation
    warn C001 summary should not exceed 50 characters
    pass T001 correct keys are used
    pass T002 test script is defined
    pass T003 directory path is absolute
    pass T004 test path '/home/psss/git/tmt/tests/execute/basic' does exist
    skip T005 legacy relevancy not detected
    skip T006 legacy 'coverage' field not detected
    skip T007 not a manual test
    skip T008 not a manual test
    pass T009 all requirements have type field

There is a broad variety of options to control what checks are
applied on tests, plans and stories:

.. code-block:: shell

    # Lint everything, everywhere
    tmt lint

    # Lint just selected plans
    tmt lint /plans/features
    tmt plans lint /plans/features

    # Change the set of checks applied - enable some, disable others
    tmt lint --enable-check T001 --disable-check C002

See the :ref:`lint-checks` page for the list of available checks
or use the ``--list-checks`` option. For the full list of options,
see ``tmt lint --help``.

.. code-block:: shell

    # All checks tmt has for tests, plans and stories
    tmt lint --list-checks

    # All checks tmt has for tests
    tmt test lint --list-checks

You should run ``tmt lint`` before pushing changes, ideally even
before you commit your changes. You can set up `pre-commit`__ to
do it for you. Add to your repository's ``.pre-commit-config.yaml``:

.. code-block:: yaml

    repos:
    - repo: https://github.com/teemtee/tmt.git
      rev: 1.23.0
      hooks:
      - id: tmt-lint

This will run ``tmt lint --source`` for all modified fmf files.
There are hooks to just check tests ``tmt-tests-lint``, plans
``tmt-plans-lint`` or stories ``tmt-stories-lint`` explicitly.
From time to time you might want to run ``pre-commit autoupdate``
to refresh config to the latest version.

__ https://pre-commit.com/#install

.. _inheritance:

Inheritance
------------------------------------------------------------------

The ``fmf`` format provides a nice flexibility regarding the file
location. Tests, plans and stories can be placed arbitrarily in
the repo. You can pick the location which best fits your project.
However, it makes sense to group similar or closely related
objects together. A thoughtful structure will not only make it
easier to find things and more quickly understand the content, it
also allows to prevent duplication of common metadata which would
be otherwise repeated many times.

Let's have a look at some tangible example. We create separate
directories for tests and plans. Under each of them there is an
additional level to group related tests or plans together:

.. code-block::

    ├── plans
    │   ├── features
    │   ├── install
    │   ├── integration
    │   ├── provision
    │   ├── remote
    │   └── sanity
    └── tests
       ├── core
       ├── full
       ├── init
       ├── lint
       ├── login
       ├── run
       ├── steps
       └── unit

Vast majority of the tests is executed using a ``./test.sh``
script which is written in ``beakerlib`` framework and almost all
tests require ``tmt`` package to be installed on the system. So
the following test metadata are common:

.. code-block:: yaml

    test: ./test.sh
    framework: beakerlib
    require: [tmt]

Instead of repating this information again and again for each test
we place a ``main.fmf`` file at the top of the ``tests`` tree:

.. code-block::

    tests
    ├── main.fmf
    ├── core
    ├── full
    ├── init
    ...

.. _virtual-tests:

Virtual Tests
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes it might be useful to reuse test code by providing
different parameter or an environment variable to the same test
script. In such cases inheritance allows to easily share the
common setup:

.. code-block:: yaml

    test: ./test.sh
    require: curl

    /fast:
        summary: Quick smoke test
        tier: 1
        duration: 1m
        environment:
            MODE: fast

    /full:
        summary: Full test set
        tier: 2
        duration: 10m
        environment:
            MODE: full

In the example above, two tests are defined, both executing the
same ``test.sh`` script but providing a different environment
variable which instructs the test to perform a different set of
actions.

.. _inherit-plans:

Inherit Plans
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If several plans share similar content it is possible to use
inheritance to prevent unnecessary duplication of the data:

.. code-block:: yaml

    discover:
        how: fmf
        url: https://github.com/teemtee/tmt
    prepare:
        how: ansible
        playbook: ansible/packages.yml
    execute:
        how: tmt

    /basic:
        summary: Quick set of basic functionality tests
        discover+:
            filter: tier:1

    /features:
        summary: Detailed tests for individual features
        discover+:
            filter: tier:2

Note that a ``+`` sign should be used if you want to extend the
parent data instead of replacing them. See the `fmf features`_
documentation for a detailed description of the hierarchy,
inheritance and merging attributes.

.. _fmf features: https://fmf.readthedocs.io/en/latest/features.html

.. _elasticity:

Elasticity
------------------------------------------------------------------

Depending on the size of your project you can choose to store all
configuration in just a single file or rather use multiple files
to store each test, plan or story separately. For example, you can
combine both the plan and tests like this:

.. code-block:: yaml

    /plan:
        summary:
            Verify that plugins are working
        discover:
            how: fmf
        provision:
            how: container
        prepare:
            how: install
            package: did
        execute:
            how: tmt

    /tests:
        /bugzilla:
            test: did --bugzilla
        /github:
            test: did --github
        /koji:
            test: did --koji

Or you can put the plan in one file and tests into another one:

.. code-block:: yaml

    # plan.fmf
    summary:
        Verify that plugins are working
    discover:
        how: fmf
    provision:
        how: container
    prepare:
        how: install
        package: did
    execute:
        how: tmt

    # tests.fmf
    /bugzilla:
        test: did --bugzilla
    /github:
        test: did --github
    /koji:
        test: did --koji

Or even each test can be defined in a separate file:

.. code-block:: yaml

    # tests/bugzilla.fmf
    test: did --bugzilla

    # tests/github.fmf
    test: did --github

    # tests/koji.fmf
    test: did --koji

You can start with a single file when the project is still small.
When some branch of the config grows too much, you can easily
extract the large content into a new separate file.

The :ref:`tree` built from the scattered files stay identical if
the same name is used for the file or directory containing the
data. For example, the ``/tests/koji`` test from the top
``main.fmf`` config could be moved to any of the following
locations without any change to the resulting `fmf` tree:

.. code-block:: yaml

    # tests.fmf
    /koji:
        test: did --koji

    # tests/main.fmf
    /koji:
        test: did --koji

    # tests/koji.fmf
    test: did --koji

    # tests/koji/main.fmf
    test: did --koji

This gives you a nice flexibility to extend the metadata when and
where needed as your project organically grows.


Multihost Testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 1.24

Support for basic server/client scenarios is now available.

The ``prepare``, ``execute``, and ``finish`` steps are able to run a
given task (test, preparation script, ansible playbook, etc.) on
several guests at once. Tasks are assigned to provisioned guests by
matching the ``where`` key from
:ref:`discover</spec/plans/discover/where>`,
:ref:`prepare</spec/plans/prepare/where>` and ``finish`` phases
with corresponding guests by their
:ref:`key and role keys</spec/plans/provision/multihost>`.
Essentially, plan author tells tmt on which guest(s) a test or
script should run by listing guest name(s) or guest role(s).

The granularity of the multihost scenario is on the step phase
level. The user may define multiple ``discover``, ``prepare`` and
``finish`` phases, and everything in them will start on given guests
at the same time when the previous phase completes. The practical
effect is, tmt does not manage synchronization on the test level:

.. code-block:: yaml

    discover:
      - name: server-setup
        how: fmf
        test:
          - /tests/A
        where:
          - server

      - name: tests
        how: fmf
        test:
          - /tests/B
          - /tests/C
        where:
          - server
          - client

In this example, first, everything from the ``server-setup`` phase
would run on guests called ``server``, while guests with the name or
role ``client`` would remain idle. When this phase completes, tmt
would move to the next one, and run everything in ``tests`` on
``server`` and ``client`` guests. The phase would be started at the
same time, more or less, but tmt will not even try to synchronize
the execution of each test from this phase. ``/tests/B`` may still
be running on ``server`` when ``/tests/C`` is already completed on
``client``.

tmt exposes information about guests and roles to all three steps in
the form of files tests and scripts can parse or import.
See the :ref:`/spec/plans/guest-topology` for details. Information
from these files can be then used to contact other guests, connect
to their services, synchronization, etc.

tmt fully supports one test being executed multiple times. This is
especially visible in the format of results, see
:ref:`/spec/plans/results`. Every test is assigned a "serial
number", if the same test appears in multiple discover phases, each
instance would be given a different serial number. The serial number
and the guest from which a result comes from are then saved for each
test result.

.. note::

    As a well-mannered project, tmt of course has a battery of tests
    to make sure the multihost support does not break down. The
    `/tests/multihost/complete`__ test may serve as an inspiration
    for your experiments.

__ https://github.com/teemtee/tmt/tree/main/tests/multihost/complete/data


Synchronization Libraries
------------------------------------------------------------------

The test-level synchronization, as described above, is not
implemented, and this is probably not going to change any time
soon. For the test-level synchronization, please use dedicated
libraries, e.g. one of the following:

  * `RHTS support`__ in Beaker ``rhts-sync-block`` and
    ``rhts-sync-set``,
  * `a beakerlib library`__ by Ondrej Moris, utilizes a shared
    storage, two-hosts only,
  * `a rhts-like distributed version`__ by Karel Srot,
  * `a native beakerlib library`__ by Dalibor Pospisil, a
    distributed version of Ondrej Moris's library, supporting any
    number of hosts.

__ https://github.com/beaker-project/rhts
__ https://github.com/beakerlib/sync/tree/master/sync
__ https://github.com/RedHat-SP-Security/keylime-tests/tree/main/Library/sync
__ https://github.com/beakerlib/ControlFlow/tree/master/sync


Current Limits
------------------------------------------------------------------

.. note::

    For the most up-to-date list of issues related to multihost,
    our Github can display all isues with the `multihost`__ label.

* requirements of all tests (:ref:`/spec/tests/require`,
  :ref:`/spec/tests/recommend`) are installed on all guests. See
  `this issue`__ for more details.
* interaction between guests provisioned by different plugins. Think
  "a server from ``podman`` plugin vs client from ``virtual``".
  This is not yet supported, see these issues: `here`__
  and `here`__.
* ``provision`` step is still running in sequence, guests are
  provisioned one by one. This is not technically necessary, and
  with tools we now have for handling parallelization of other
  steps, provisioning deserves the same treatment, resulting in,
  hopefully, a noticeable speed up (especially with plugins like
  ``beaker`` or ``artemis``).

__ https://github.com/teemtee/tmt/labels/multihost
__ https://github.com/teemtee/tmt/issues/2010
__ https://github.com/teemtee/tmt/issues/2047
__ https://github.com/teemtee/tmt/issues/2046
