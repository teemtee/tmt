.. _contribute:

==================
    Contribute
==================


Introduction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Feel free and welcome to contribute to this project. You can start
with filing issues and ideas for improvement in GitHub tracker__.
Before creating a new issue you might want to check the existing
issues to prevent filing a duplicate. Important issues affecting
many users are marked with the `known issue`__ label.

Our favorite thoughts from The Zen of Python:

* Beautiful is better than ugly.
* Simple is better than complex.
* Readability counts.

We respect the `PEP8`__ Style Guide for Python Code. Here's a
couple of recommendations to keep on mind when writing code:

* Maximum line length is 99 for code and 72 for documentation.
* Comments should be complete sentences.
* The first word should be capitalized (unless identifier).
* When using hanging indent, the first line should be empty.
* The closing brace/bracket/parenthesis on multiline constructs
  is under the first non-whitespace character of the last line.

When generating user messages use the whole sentence with the
first word capitalized and enclose any names in single quotes:

.. code-block:: python

    self.warn(f"File '{path}' not found.")

__ https://github.com/teemtee/tmt/issues
__ https://github.com/teemtee/tmt/issues?q=label%3A%22known+issue%22
__ https://www.python.org/dev/peps/pep-0008/


Commits
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is challenging to be both concise and descriptive, but that is
what a well-written summary should do. Consider the commit message
as something that will be pasted into release notes:

* The first line should have up to 50 characters.
* Complete sentence with the first word capitalized.
* Should concisely describe the purpose of the patch.
* Do not prefix the message with file or module names.
* Other details should be separated by a blank line.

Why should I care?

* It helps others (and yourself) find relevant commits quickly.
* The summary line will be re-used later (e.g. for rpm changelog).
* Some tools do not handle wrapping, so it is then hard to read.
* You will make the maintainers happy to read beautiful commits :)

You can get some more context in the `stackoverflow`__ article.

__ https://stackoverflow.com/questions/2290016/

.. _develop:

Develop
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In order to experiment, play with the latest bits and develop
improvements it is best to use a virtual environment. Make sure
that you have all required packages installed on your box:

.. code-block:: shell

    make develop

Create a development virtual environment with hatch:

.. code-block:: shell

    git clone https://github.com/teemtee/tmt
    cd tmt
    hatch env create dev

Enter the environment by running:

.. code-block:: shell

    hatch -e dev shell

When interacting from within the development environment with
services with internal certificates, you need to export the
following environment variable:

.. code-block:: shell

    export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt

Install the ``pre-commit`` script to run all available checks for
your commits to the project:

.. code-block:: shell

    pre-commit install


Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every code change should be accompanied by tests covering the new
feature or affected code area. It's possible to write new tests or
extend the existing ones.

If writing a test is not feasible for you, explain the reason in
the pull request. If possible, the maintainers will help with
creating needed test coverage. You might also want to add the
``help wanted`` and ``tests needed`` labels to bring a bit more
attention to your pull request.

Run the default set of tests directly on your localhost:

.. code-block:: shell

    tmt run

Run selected tests or plans in verbose mode:

.. code-block:: shell

    tmt run --verbose plan --name basic
    tmt run -v test -n smoke

You might want to set some useful environment variables when
working on ``tmt`` tests, for example ``TMT_FEELING_SAFE`` to
allow the ``local`` provision method or ``TMT_SHOW_TRACEBACK`` to
show the full details for all failures. Consider installing the
`direnv`__ command which can take care of these for you.

__ https://direnv.net/#basic-installation


Unit Tests
------------------------------------------------------------------

To run unit tests in hatch environment using pytest and generate coverage report:

.. code-block:: shell

    make coverage

To see all available scripts for running tests in hatch test virtual environments:

.. code-block:: shell

    hatch env show test

To run 'unit' script for example, run:

.. code-block:: shell

    hatch run test:unit

When running tests using hatch, there are multiple virtual environments
available, each using a different Python interpreter
(generally the lowest and highest version supported).
To run the tests in all environments, install the required Python
versions. For example:

.. code-block:: shell

    dnf install python3.9 python3.11

.. note::

   When adding new unit tests, do not create class-based tests derived from
   ``unittest.TestCase`` class. Such classes do not play well with Pytest's
   fixtures, see https://docs.pytest.org/en/7.1.x/how-to/unittest.html for
   details.

.. _provision-methods:

Provision Methods
------------------------------------------------------------------

Tests which exercise multiple provision methods should use the
``PROVISION_HOW`` environment variable to select which provision
method should be exercised during their execution. This variable
is likely to have ``local`` set as the default value in the test
script to execute directly on the test runner as the default
scenario. If a test does not support the ``local`` provision
method make sure to use the ``provision-only`` tag so that the
test in question is excluded from the regular plans.

The following tags can be used to enable given test under the
respective provision method plan:

provision-artemis
    For tests checking the :ref:`/spec/plans/provision/artemis`
    plugin functionality.

provision-beaker
    For tests checking the :ref:`/spec/plans/provision/beaker`
    plugin functionality using the ``mrack`` plugin.

provision-connect
    For tests checking the :ref:`/spec/plans/provision/connect`
    plugin functionality.

provision-container
    For tests checking the :ref:`/spec/plans/provision/container`
    provision method using the ``podman`` plugin.

provision-virtual
    For tests checking the :ref:`/spec/plans/provision/virtual`
    provision method using the ``testcloud`` plugin.

provision-ssh
    Tests which are not tied to a specific provision method but
    should be executed for all provision methods which are using
    ``ssh`` to connect to guests.

provision-only
    Used to mark tests which are suitable to be run only under
    specific provision methods. These will be excluded from
    regular plans.


Tags
------------------------------------------------------------------
In addition to the tags related to the :ref:`provision-methods` tags,
following are used in the tests:

as_root
    Test has to be executed as the root (or privileged) user to
    execute properly.  For example test adds user, changes the
    system, etc.

beakerlib
    Test integration of `BeakerLib`__ framework with the tmt.

integration
    Test using `requre`__ to mock connections to other servers.

__ https://github.com/beakerlib/beakerlib
__ https://requre.readthedocs.io/en/latest/


Images
------------------------------------------------------------------

Tests which exercise the :ref:`/spec/plans/provision/container`
provisioning plugin with various guest environments should use the
custom-built set of container images rather than using the upstream ones
directly. We built custom images to have better control over the initial
environment setup, especially when it comes to essential requirements
and assumption tmt makes about the guest setup. The naming scheme also
provides better information about content of these images when compared
to very varied upstream locations.

Naming scheme
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

All our test images follow a simple naming pattern:

    ``localhost/tmt/tests/BACKEND/DISTRIBUTION/RELEASE/EXTRAS:TAG``

``localhost/tmt/tests``
    To make it clear the image was built locally, it is owned by tmt,
    and it is not packaging tmt but serves for testing purposes only.

``BACKEND``
    There are various kinds of "images", the most well-known ones would
    be Docker/Podman images, their names would contain ``container``
    flag, and QCOW2 images for VMs which would be labeled with
    ``virtual``.

``DISTRIBUTION``
    A lower-cased name of the Linux distribution hosted in the image:
    ``fedora``, ``ubuntu``, ``alpine``, etc.

``RELEASE``
    A release of the ``DISTRIBUTION``: ``7`` for CentOS 7, ``stream9``
    for CentOS Stream 9, or ``40``, ``rawhide`` and even ``coreos`` for
    Fedora.

``EXTRAS``
    Additional flags describing a "flavor" of the image:

    * ``upstream`` images are identical to an upstream image, adding no
      special setup on top of the upstream.
    * ``unprivileged`` images come with password-less ``sudo`` setup and
      may be used when unprivileged access is part of the test.
    * ``ostree`` images are Fedora CoreOS that simulate being deployed
      by `ostree`__.

``TAG``
    Usually ``latest`` as in "the latest image for this distro, release
    and extra flags".

    .. note::
        So far we do not have much use for other tags besides
        ``latest``. ``stable`` used for Fedora CoreOS images will
        probably go away in favor of ``latest``.

For example, the following images can be found:

.. code-block::

    # Latest Alpine, with added Bash to simulate proper essential setup:
    localhost/tmt/tests/container/alpine

    # Various CentOS releases:
    localhost/tmt/tests/container/centos/7
    localhost/tmt/tests/container/centos/stream9

    # Fedora rawhide, with dnf5 pre-installed:
    localhost/tmt/tests/container/fedora/rawhide

    # Same, but with password-less sudo set up:
    localhost/tmt/tests/container/fedora/rawhide/unprivileged

__ https://ostreedev.github.io/ostree/

To build these images, run the following:

.. code-block:: shell

    # Build all images...
    make images-tests

    # ... or just a single one:
    make images-tests/tmt/tests/container/fedora/rawhide:latest

Tests that need to use various container images should trigger this
command before running the actual test cases:

.. code-block:: bash

    rlRun "make -C images-tests"

To list built container images, run the following:

.. code-block:: shell

    podman images | grep 'localhost/tmt/tests/' | sort

To remove these images from your local system, run the following:

.. code-block:: shell

    make clean-test-images


.. _docs:

Docs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When submitting a change affecting user experience it's always
good to include respective documentation. You can add or update
the :ref:`specification`, extend the :ref:`examples` or write a
new chapter for the user :ref:`guide`.

tmt documentation is written with `reStructuredText`__ and built
with `Sphinx`__. Various features of both reST and Sphinx are used
widely in tmt documentation, from inline markup to references. Feel
free to use them as well to link new or updated documentation to relevant
parts, to highlight important points, or to provide helpful examples.

A couple of best practices when updating documentation:

* When referring to a plugin, its options or documentation, prefer
  reference to ``/plugins/STEP/PLUGIN`` rather than to older
  ``/spec/plans/STEP/PLUGIN``:

  .. code-block:: rest

    # This is good:
    :ref:`/plugins/prepare/ansible`

    # If the user-facing plugin name differs from the Python one,
    # or if you need capitalize the first letter:
    :ref:`Beaker</plugins/provision/beaker>`

    # This should be avoided:
    :ref:`/spec/plans/prepare/ansible`
* Design the plugin docstrings and help texts as if they are to be
  rendered by Sphinx, i.e. make use of ReST goodies: literals for
  literals - metavars, values, names of environment variables, commands,
  keys, etc., ``code-block`` for blocks of code or examples. It leads to
  better HTML docs and tmt has a nice CLI renderer as well, therefore
  there is no need to compromise for the sake of CLI.
* Use full sentences, i.e. capital letters at the beginning & a full
  stop at the end.
* Use Python multiline strings rather than joining multiple strings over
  several lines. It often leads to leading and/or trailing whitespace
  characters that are easy to miss.
* Plugin docstring provides the bulk of its CLI help and HTML
  documentation. It should describe what the plugin does.
* Other than trivial use cases and keys deserve an example or two.
* Unless there's an important difference, describe the plugin's
  configuration in terms of fmf rather than CLI. It is easy to map fmf
  to CLI options, and fmf makes a better example for someone writing fmf
  files.
* When referring to plugin configuration in user-facing docs, speak
  about "keys": "``playbook`` key of ``prepare/ansible`` plugin". Keys
  are mapped 1:1 to CLI options, let's make sure we avoid polluting docs
  with "fields", "settings" and other synonyms.
* A metavar should represent the semantic of the expected value, i.e.
  ``--file PATH`` is better than ``--file FILE``,
  ``--playbook PATH|URL`` is better than ``--playbook PLAYBOOK``.
* If there is a default value, it belongs to the ``default=`` parameter
  of :py:func:`tmt.utils.field`, and the help text should not mention it
  because the "Default is ..." sentence can be easily added
  automatically and rendered correctly with ```show_default=True``.
* When showing an example of plugin configuration, include also an
  example for the command line:

  .. code-block:: rest

     Run a single playbook on the guest:

     .. code-block:: yaml

        prepare:
            how: ansible
            playbook: ansible/packages.yml

     .. code-block:: shell

        prepare --how ansible --playbook ansible/packages.yml
* Do not use ``:caption:`` directive of ``code-block``, it is understod
  by Sphinx only and ``docutils`` package cannot handle it.

__ https://www.sphinx-doc.org/en/master/usage/restructuredtext/index.html
__ https://www.sphinx-doc.org/en/master/

Examples
------------------------------------------------------------------

By default, examples provided in the specification stories are
rendered as ``yaml``. In order to select a different syntax
highlighting schema add ``# syntax: <format>``, for example:

.. code-block:: shell

    # syntax: shell

Building documentation is then quite straightforward:

.. code-block:: shell

    make docs

Find the resulting html pages under the ``docs/_build/html``
folder.

Visual themes
------------------------------------------------------------------

Use the ``TMT_DOCS_THEME`` variable to easily pick custom theme.
If specified, ``make docs`` would use this theme for documentation
rendering by Sphinx. The theme must be installed manually, ``make
docs`` will not do so. Variable expects two strings, separated by
a colon (``:``): theme package name, and theme name.

.. code-block:: shell

    # Sphinx book theme, sphinx-book-theme:
    TMT_DOCS_THEME="sphinx_book_theme:sphinx_book_theme" make docs

    # Renku theme, renku-sphinx-theme - note that package name
    # and theme name are *not* the same string:
    TMT_DOCS_THEME="renku_sphinx_theme:renku" make docs

By default, ``docs/_static/tmt-custom.css`` provides additional tweaks
to the documentation theme. Use the ``TMT_DOCS_CUSTOM_HTML_STYLE``
variable to include additional file:

.. code-block:: shell

    $ cat docs/_static/custom.local.css
    /* Make content wider on my wider screen */
    .wy-nav-content {
        max-width: 1200px !important;
    }

    TMT_DOCS_CUSTOM_HTML_STYLE=custom.local.css make docs

.. note::

    The custom CSS file specified by ``TMT_DOCS_CUSTOM_HTML_STYLE``
    is included **before** the built-in ``tmt-custom.css``, therefore to
    override theme CSS, it is recommended to add ``!important`` flag.


Pull Requests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When submitting a new pull request which is not completely ready
for merging but you would like to get an early feedback on the
concept, use the GitHub feature to mark it as a ``Draft`` rather
than using the ``WIP`` prefix in the summary.

During the pull request review it is recommended to add new
commits with your changes on the top of the branch instead of
amending the original commit and doing a force push. This will
make it easier for the reviewers to see what has recently changed.

Once the pull request has been successfully reviewed and all tests
passed, please rebase on the latest ``main`` branch content and
squash the changes into a single commit. Use multiple commits to
group relevant code changes if the pull request is too large for a
single commit.

If the pull request addresses an existing issue, mention it using
one of the automatically `parsed formats`__ so that it is linked
to it, for example:

.. code-block:: markdown

    Fix #1234.

By default only a core set of tests is executed against a newly
created pull request and its updates to verify basic sanity of the
change. Once the pull request content is ready for a thorough
testing add the ``full test`` label and make sure that the
``discuss`` label is not present. All future changes of the pull
request will be tested with the full test coverage. For changes
related to documentation only the full test suite is not required.

__ https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/using-keywords-in-issues-and-pull-requests#linking-a-pull-request-to-an-issue

.. _checklist:

Checklist
------------------------------------------------------------------

The following checklist template is automatically added to the
new pull request description to easily track progress of the
implementation and prevent forgetting about essential steps to be
completed before it is merged. Feel free to remove those which are
irrelevant for your change.

.. code-block:: markdown

    Pull Request Checklist

    * [ ] implement the feature
    * [ ] write the documentation
    * [ ] extend the test coverage
    * [ ] update the specification
    * [ ] adjust plugin docstring
    * [ ] modify the json schema
    * [ ] mention the version
    * [ ] include a release note

The version should be mentioned in the specification and a release
note should be included when a new essential feature is added or
an important change is introduced so that users can easily check
whether given functionality is already available in their package:

.. code-block:: rst

    .. versionadded:: 1.23

.. _review:

Review
------------------------------------------------------------------

Code review is an essential part of the workflow. It ensures good
quality of the code and prevents introducing regressions, but it
also brings some additional benefits: By reading code written by
others you can learn new stuff and get inspired for your own code.
Each completed pull request review helps you, little by little, to
get familiar with larger part of the project code and empowers you
to contribute more easily in the future.

For instructions how to locally try a change on your laptop see
the :ref:`develop` section. Basically just enable the development
environment and check out the pull request branch or use the
`github cli`__ to check out code from a fork repository:

.. code-block:: shell

    hatch -e dev shell         # enable the dev environment
    git checkout the-feature   # if branch is in the tmt repo
    gh pr checkout 1234        # check out branch from a fork

It is also possible to directly install packages freshly built by
Packit for given pull request. See the respective Packit check for
detailed installation instructions.

Note that you don't have to always read the whole change. There
are several ways how to provide feedback on the pull request:

* check how the **documentation** would be rendered in the
  ``docs/readthedocs.org`` pull request check, look for typos,
  identify wording which is confusing or not clear, point out that
  documentation is completely missing for some area
* remind a forgotten item from the :ref:`checklist`, for example
  suggest writing a release note for a new significant feature
  which should be highlighted to users
* verify just the **functionality**, make sure it works as
  expected and confirm it in a short comment, provide a simple
  reproducer when something is broken
* review only the newly added **test case**, verify that the test
  works as expected and properly verifies the functionality

Even partial review which happens sooner is beneficial, saves
time. Every single comment helps to improve and move the project
forward. No question is a dumb question. Every feedback counts!

__ https://cli.github.com


Merging
------------------------------------------------------------------

Pull request merging is done by one of maintainers who have a good
overview of the whole code. Maintainer who will take care of
the process will assign themselves to the pull request.
Before merging it's good to check the following:

* New test coverage added if appropriate, all tests passed
* Documentation has been added or updated where appropriate
* Commit messages are sane, commits are reasonably squashed
* At least one positive review provided by the maintainers
* Merge commits are not used, rebase on the ``main`` instead

Pull requests which should not or cannot be merged are marked with
the ``blocked`` label. For complex topics which need more eyes to
review and discuss before merging use the ``discuss`` label.


Makefile
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There are several Makefile targets defined to make the common
daily tasks easy & efficient:

make test
    Execute the unit test suite.

make smoke
    Perform quick basic functionality test.

make coverage
    Run the test suite under coverage and report results.

make docs
    Build documentation.

make packages
    Build rpm and srpm packages.

make images
    Build container images.

make tags
    Create or update the Vim ``tags`` file for quick searching.
    You might want to use ``set tags=./tags;`` in your ``.vimrc``
    to enable parent directory search for the tags file as well.

make clean
    Cleanup all temporary files.


Release
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``tmt`` project is released monthly. If there are urgent
changes which need to be released quickly, a hotfix release may be
created to address the important problem sooner.


Regular
------------------------------------------------------------------

Follow the steps below to create a new major or minor release:

* Update ``overview.rst`` with new contributors since the last release
* Review the release notes in ``releases.rst``, update as needed
* Add a ``Release x.y.z`` commit, empty if needed: ``git commit --allow-empty -m "Release x.y.z"``
* Create a pull request with the commit, ensure tests pass, merge it
* Move the ``fedora`` branch to point to the new release
* Tag the commit with ``x.y.z``, push tags ``git push --tags``

Create a new `github release`__ based on the tag above

* Mention the most important changes in the name, do not include version
* Use ``;`` as a delimiter, when multiple items are mentioned in the name
* Push the "Generate release notes" button to create the content
* Prepend the "See the `release notes`__ for the list of interesting changes." line
* Publish the release, check Fedora `pull requests`__, make sure tests pass and merge

Finally, if everything went well:

* Close the corresponding release milestone
* Once the non development `copr build`__ is completed, move the
  ``quay`` branch to point to the release commit as well to build
  fresh `container images`__.

Handle manually what did not went well:

* If the automation triggered by publishing the new github release
  was not successful, publish the fresh code to the `pypi`__
  repository manually using ``make wheel && make upload``
* If there was a problem with creating Fedora pull requests, you
  can trigger them manually using ``/packit propose-downstream``
  in any open issue.

__ https://github.com/teemtee/tmt/releases/
__ https://tmt.readthedocs.io/en/stable/releases.html
__ https://src.fedoraproject.org/rpms/tmt/pull-requests
__ https://copr.fedorainfracloud.org/coprs/g/teemtee/tmt/builds/
__ https://quay.io/repository/teemtee/tmt
__ https://pypi.org/project/tmt/


Hotfix
------------------------------------------------------------------

The following steps should be followed when an important urgent
fix needs to be released before the regular schedule:

* Create a new branch from the ``fedora`` branch
* Use ``git cherry-pick`` to apply the selected change
* Mention the hotfix release on the release page
* Add a ``Release x.y.z`` commit, empty if needed: ``git commit --allow-empty -m "Release x.y.z"``
* Create a new pull request with the target branch set to ``fedora``
* Make sure that tests pass and merge the pull request
* Tag the commit and publish the release in the same way as for
  regular release
* Create a pull request with the hotfix release notes changes
