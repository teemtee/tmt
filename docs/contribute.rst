.. _contribute:

==================
    Contribute
==================


Introduction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Feel free and welcome to contribute to this project. You can start
with filing issues and ideas for improvement in GitHub tracker__.
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

__ https://github.com/teemtee/tmt
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

__ http://stackoverflow.com/questions/2290016/


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


Full Test
------------------------------------------------------------------

.. warning::

    This full test approach is being obsoleted.
    See the :ref:`provision-methods` section for details.

Build the rpms and execute the whole test coverage, including
tests which need the full virtualization support:

.. code-block:: shell

    make build-deps
    make rpm
    tmt -c how=full run

This would install the freshly built rpms on your laptop. In order
to run the full test suite more safely under a virtual machine run
the full test suite wrapper against the desired branch:

.. code-block:: shell

    cd tests/full
    tmt run --environment BRANCH=target

Or schedule the full test suite under an external test system:

.. code-block:: shell

    cd tests/full
    tmt test export --fmf-id | wow fedora-35 x86_64 --fmf-id - --taskparam=BRANCH=target

Or run local modifications copied to the virtual machine. Because this
requires changes outside of the fmf root you need to run make
which tars sources to the expected location:

.. code-block:: shell

    cd tests/full
    make test

Similar as above but run only tests which don't run for merge requests:

.. code-block:: shell

    cd tests/full
    make test-complement


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


Docs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When submitting a change affecting user experience it's always
good to include respective documentation. You can add or update
the :ref:`specification`, extend the :ref:`examples` or write a
new chapter for the user :ref:`guide`.

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

If the pull request addresses an existing issue, mention it using
one of the automatically parsed formats so that it is linked to
it, for example:

.. code-block:: markdown

    Fix #1234.

By default only a core set of tests is executed against a newly
created pull request and its updates to verify basic sanity of the
change. Once the pull request content is ready for a thorough
testing add the ``full test`` label and make sure that the
``discuss`` label is not present. All future changes of the pull
request will be tested with the full test coverage.


Merging
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

Follow the steps below to create a new major or minor release:

* Run the full test coverage using ``tmt -c how=full run``
* Use ``git log --oneline --no-decorate x.y-1..`` to generate the changelog
* Update ``overview.rst`` with new contributors since the last release
* Review the release notes in ``releases.rst``, update as needed
* Add a ``Release tmt-x.y.0`` commit with the specfile update
* Create a pull request with the commit, ensure tests pass, merge it

Release a new package to Fedora and EPEL repositories:

* Move the ``fedora`` branch to point to the new release
* Tag the commit with ``x.y.0``, push tags ``git push --tags``
* Create a new `github release`__ based on the tag above
* Check Fedora `pull requests`__, make sure tests pass and merge

Finally, if everything went well:

* Close the corresponding release milestone
* Once the non development `copr build`__ is completed, move the
  ``quay`` branch to point to the release commit as well to build
  fresh container images.

Handle manually what did not went well:

* If the automation triggered by publishing the new github release
  was not successful, publish the fresh code to the `pypi`__
  repository manually using ``make wheel && make upload``
* If there was a problem with creating Fedora pull requests, you
  can trigger them manually using ``/packit propose-downstream``
  in any open issue.

__ https://github.com/teemtee/tmt/releases/
__ https://src.fedoraproject.org/rpms/tmt/pull-requests
__ https://copr.fedorainfracloud.org/coprs/g/teemtee/tmt/builds/
__ https://pypi.org/project/tmt/
