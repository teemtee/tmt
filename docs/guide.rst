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
straightforward. No worry, the :ref:`/stories/install/minimal`
package has just a few dependencies:

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

    tmt --feeling-safe run --all provision --how local

Note that the extra ``--feeling-safe`` option is needed for the
:ref:`/plugins/provision/local` provision plugin as it can be
dangerous to execute unknown code directly on your system. If
you're afraid that the test could break your machine or just want
to keep your environment clean, run it in a container instead:

.. code-block:: shell

    sudo dnf install -y tmt+provision-container
    tmt run -a provision -h container

Or even in a full virtual machine if the container environment is
not enough. We'll use the :ref:`libvirt<libvirt>` to start a new
virtual machine on your localhost. Be ready for a bit more
dependencies here:

.. code-block:: shell

    sudo dnf install -y tmt+provision-virtual
    tmt run -a provision -h virtual

Don't care about the disk space? Simply install ``tmt+all`` and
you'll get :ref:`/stories/install/all` available functionality at
hand. Check the help to list all supported provision methods:

.. code-block:: shell

    sudo dnf install tmt+all
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
:ref:`inheritance` or :ref:`elasticity` which help to maintain
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
possible to use the :ref:`/plugins/prepare/install` method for
simple package installations, :ref:`/plugins/prepare/ansible`
for more complex system setup or :ref:`/plugins/prepare/shell`
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

Instead of writing the plan and test metadata manually, you might
want to simply apply the ``base`` template which contains the plan
mentioned above together with a test example including both test
metadata and test script skeleton for inspiration:

.. code-block:: shell

    tmt init --template base

Similar to plans, it is possible to choose an arbitrary name for
the test. Just make sure the ``test`` key is defined. However, to
organize the metadata efficiently it is recommended to keep tests
and plans under separate folders, e.g. ``tests`` and ``plans``.
This will also allow you to use :ref:`inheritance` to prevent
unnecessary data duplication.


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
      - tmt tests show -v
      - tmt tests show -vvv
      - tmt tests show --verbose

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


.. _organize-data:

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

As for now there are two test `templates`__ available, ``shell``
for simple scripts written in shell and ``beakerlib`` with a basic
skeleton demonstrating essential functions of this shell-level
testing framework. If you want to be faster, specify the desired
template directly on the command line using ``--template`` or
``-t``:

__ https://github.com/teemtee/tmt/tree/main/tmt/templates

.. code-block:: shell

    $ tmt test create --template shell /tests/smoke
    $ tmt test create -t beakerlib /tests/smoke

To create multiple tests at once, you can specify multiple names
at the same time:

.. code-block:: shell

    $ tmt tests create -t shell /tests/core /tests/base /tests/full

If you'd like to link relevant issues when creating a test, specify
the links via ``[RELATION:]TARGET`` on the command line using
``--link``:

.. code-block:: shell

    $ tmt test create /tests/smoke --link foo
    $ tmt test create /tests/smoke --link foo --link verifies:https://foo.com/a/b/c

In a similar way, the ``tmt plan create`` command can be used to
create a new plan with templates:

.. code-block:: shell

    tmt plan create --template mini /plans/smoke
    tmt plan create -t full /plans/features

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


.. _custom_templates:

Custom Templates
------------------------------------------------------------------

If you create new tests often, you might want to create a custom
template in order to get quickly started with a new test skeleton
tailored exactly to your needs. The same applies for plans and
stories.

Templates can be defined inside the config directory
``TMT_CONFIG_DIR`` under the ``templates`` subdirectory. If the
config directory is not explicitly set, the default config
directory ``~/.config/tmt/templates`` is used. Use the following
directory structure when creating custom templates:

* ``~/.config/tmt/templates/story`` for story metadata
* ``~/.config/tmt/templates/plan`` for plan metadata
* ``~/.config/tmt/templates/test`` for test metadata
* ``~/.config/tmt/templates/script`` for test scripts

We use Jinja for templates, so your template files must have the
``.j2`` file extension. You can also apply default Jinja filters
to your templates.

To use your custom templates, use the ``--template`` option with
your template name. For example, if you have created a
``feature.j2`` story template:

.. code-block:: shell

    tmt stories create --template feature /stories/download
    tmt stories create -t feature /stories/upload

In the very same way you can create your custom templates for new
plans and tests. Tests are a bit special as they also need a
script template in addition to the test metadata. By default, both
test metadata and test script use the same template name, so for a
``web`` template the command line would look like this:

.. code-block:: shell

    tmt tests create --template web /tests/server
    tmt tests create -t web /tests/client

If you want to use a different template for the test script, use
the ``--script`` option. For example, it might be useful to have
a separate ``multihost.j2`` template for complex scenarios where
multiple guests are involved:

.. code-block:: shell

    tmt tests create --template web --script multihost /tests/download
    tmt tests create -t web -s multihost /tests/upload

Sometimes it might be useful to maintain common templates on a
single place and share them across the team. To use a remote
template just provide the URL to the ``--template`` option. If you
want to use a custom remote template for tests, you need to use
both ``--template`` and ``--script`` options. For example:

.. code-block:: shell

    tmt tests create \
        --template https://team.repo/web.j2 \
        --script https://team.repo/multihost.j2 \
        /tests/download

.. versionadded:: 1.30


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
    tmt tests lint --list-checks

You should run ``tmt lint`` before pushing changes, ideally even
before you commit your changes. You can set up `pre-commit`__ to
do it for you. Add to your repository's ``.pre-commit-config.yaml``:

.. code-block:: yaml

    repos:
    - repo: https://github.com/teemtee/tmt.git
      rev: 1.29.0
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

Instead of repeating this information again and again for each test
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


.. _link-issues:

Link Issues
------------------------------------------------------------------

You can link issues to the test or plan that covers it. This can
be done either directly during creation of a new test or plan, or
later using the ``tmt link`` command:

.. code-block:: shell

    tmt link --link verifies:https://issues.redhat.com/browse/YOUR-ISSUE tests/core/smoke

In order to enable this feature, create a configuration file
``.config/tmt/link.fmf`` and define an ``issue-tracker`` section
there. Once the configuration is present, it enables the linking
on its own, no further action is needed. The section should have
the following format:

.. code-block:: yaml

    issue-tracker:
      - type: jira
        url: https://issues.redhat.com
        tmt-web-url: https://tmt.testing-farm.io/
        token: <YOUR_PERSONAL_JIRA_TOKEN>

The ``type`` key specifies the type of the issue tracking service
you want to link to (so far only Jira is supported). The ``url``
is the URL of said service. The ``tmt-web-url`` is the URL of the
service that presents tmt metadata in a human-readable form. The
``token`` is a personal token that is used to authenticate the
user. How to obtain this token is described `here
<https://support.atlassian.com/atlassian-account/docs/
manage-api-tokens-for-your-atlassian-account/#Create-an-API-token>`_
(please note that this can vary if you use custom Jira instance).

Once the link is attached to the respective Jira, clicking on it
will take you to the tmt web service with test or plan details.
Here's an example `test`__ and `plan`__. It is also possible to
reference both `test and plan`__ in a single link.

__ https://tmt.testing-farm.io/?test-url=https%3A%2F%2Fgithub.com%2Fteemtee%2Ftmt.git&test-name=%2Ftests%2Fcore%2Fescaping&test-ref=main
__ https://tmt.testing-farm.io/?plan-url=https%3A%2F%2Fgithub.com%2Fteemtee%2Ftmt.git&plan-name=%2Fplans%2Ffeatures%2Fcore&plan-ref=main
__ https://tmt.testing-farm.io/?test-url=https%3A%2F%2Fgithub.com%2Fteemtee%2Ftmt.git&test-name=%2Ftests%2Fcore%2Flink&test-ref=main&plan-url=https%3A%2F%2Fgithub.com%2Fteemtee%2Ftmt.git&plan-name=%2Fplans%2Ffeatures%2Fcore&plan-ref=main

.. versionadded:: 1.37


.. _share-tests:

Share Tests
------------------------------------------------------------------

Tests can be shared across different repositories, significantly
enhancing efficiency, reducing data duplication, and improving
maintainability in the testing workflow.

tmt allows references to external repositories directly within the
``discover`` step of the plan. By specifying the URL of a remote
git repository, tmt can fetch and integrate tests defined within
that repository.

.. code-block:: yaml

    discover:
      # Fetch common tests from a shared repository
      - name: core-tests
        how: fmf
        url: https://github.com/my-org/core-tests.git

      # Discover tests located within this project's own repository
      - name: project-specific
        how: fmf


.. _adjust-metadata:

Adjust Metadata
------------------------------------------------------------------

Sometimes metadata needs to be adjusted based on the context.
For example, the user might want to enable a test only for a
specific architecture or skip a plan when running in a container.
The core attribute :ref:`/spec/core/adjust` provides a flexible
way to achieve this. It allows to modify various attributes of
the tests, plans, or stories depending on the current
:ref:`/spec/context`.

This feature helps with creating adaptable and reusable metadata,
reducing the need for multiple versions of similar configurations.
Rules can be defined to conditionally change attributes
like ``enabled``, ``environment``, ``require`` or even the
test script itself.

.. code-block:: yaml

    # Disable a test for older distros
    enabled: true
    adjust:
        enabled: false
        when: distro < fedora-33
        because: the feature was added in Fedora 33


.. _anchors-aliases:

Anchors and Aliases
------------------------------------------------------------------

When you need to specify the same variable multiple times in a
single file, the ``yaml`` feature called `Anchors and Aliases`__
can come handy. You can define an anchor before an item to save
it for future usage with an `alias`__.

.. code-block:: yaml

    # Example of an anchor:
    discover:
        how: fmf
        test: &stable
          - first
          - second

    # Which you can then use later in the same file as an alias:
    discover:
        how: fmf
        exclude: *stable

__ https://yaml.org/spec/1.2.2/#3222-anchors-and-aliases
__ https://yaml.org/spec/1.2.2/#alias-nodes

.. _git-metadata:

Git Metadata
------------------------------------------------------------------

In order to save space and bandwidth, the ``.git`` directory is
not synced to the guest by default. If you want to have it
available, use the respective ``discover`` step option to have it
copied to the guest.

.. code-block:: yaml

    discover:
      - name: Keep git for fmf discovery
        how: fmf
        sync-repo: true

.. code-block:: yaml

    discover:
      - name: Keep git for shell discovery
        how: shell
        keep-git-metadata: true

.. note::

    Git metadata cannot be copied for the ``prepare`` or
    ``finish`` steps yet.


.. _when-config:

Conditional step configuration
------------------------------

.. versionadded:: 1.40

Sometimes, the plan is expected to cover a broad set of environments;
however, some step configurations may not be applicable everywhere.
While :ref:`/spec/core/adjust` can be used to construct the plan
in this way, it soon becomes difficult to read.

Using the ``when`` key makes it easier to restrict a step configuration
to run only if any of the specified rules matches.
The syntax is the same as in ``adjust`` and :ref:`/spec/context`.

.. code-block:: yaml

    prepare:
      - name: Prepare config to run only on Fedora
        when: distro == fedora
        how: shell
        script: ./fedora_specific.sh
      - name: Runs always
        how: shell
        script: ./setup.sh
      - name: More rules in 'when' key
        how: shell
        script: ./something.sh
        when:
        - arch != x86_64
        - initiator == human && distro == fedora


.. _multihost-testing:

Multihost Testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 1.24

Support for basic server/client scenarios is now available.

The ``prepare``, ``execute``, and ``finish`` steps are able to run a
given task (test, preparation script, ansible playbook, etc.) on
several guests at once. Tasks are assigned to provisioned guests by
matching the ``where`` key from
:ref:`discover</spec/plans/discover/where>`,
:ref:`prepare</spec/plans/prepare/where>` and
:ref:`finish</spec/plans/finish/where>`
phases with corresponding guests by their
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
:ref:`/spec/results`. Every test is assigned a "serial
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

Rerunning failed tests of previously executed runs
------------------------------------------------------------------

Executing failed tests again after fixing them is now possible
with `tmt run --all --again tests --failed-only`.

This is only possible when you have the run directory available
and `--id` argument provided (or use `--last`) as it needs the data from
execute step to select only failed test cases. After new execute step,
tmt will again merge the results from the previous run with the new ones
to keep all the data for full report.

.. code-block:: shell

    $ tmt run
    # Some tests fail, some pass

    $ tmt run --last --again discover tests --failed-only
    # Discover tests to rerun

    $ tmt run --all --last --again tests --failed-only
    # Run all failed tests again

.. versionadded:: 1.34


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
  * `redis server`__ by Jan Scotka, a simple key-value exchange
    solution between machines. The primary purpose is data
    transfer. It is not a library prepared for synchronization,
    but it's possible to use it as well. See the example to learn
    how to set up a redis server and use it.

__ https://github.com/beaker-project/rhts
__ https://github.com/beakerlib/sync/tree/master/sync
__ https://github.com/RedHat-SP-Security/keylime-tests/tree/main/Library/sync
__ https://github.com/beakerlib/ControlFlow/tree/master/sync
__ https://github.com/teemtee/tmt/tree/main/examples/redis


Current Limits
------------------------------------------------------------------

.. note::

    For the most up-to-date list of issues related to multihost,
    our Github can display all issues with the `multihost`__ label.

* interaction between guests provisioned by different plugins. Think
  "a server from ``podman`` plugin vs client from ``virtual``".
  This is not yet supported, see `this issue`__.

__ https://github.com/teemtee/tmt/labels/multihost
__ https://github.com/teemtee/tmt/issues/2047


.. include:: guide/test-runner.inc.rst
.. include:: guide/guest-preparation.inc.rst
