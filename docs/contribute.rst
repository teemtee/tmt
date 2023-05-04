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

    sudo dnf install gcc make git python3-docutils {python3,libvirt,krb5,libpq}-devel jq

In case you're using Centos Stream 9 system you need to enable CRB
repository first to make all the necessary packages available:

.. code-block:: shell

    sudo dnf config-manager --set-enabled crb # for CentOS Stream 9

For CentOS Stream 8 install also:

.. code-block:: shell

    sudo dnf install python3-virtualenv

Install ``python3-virtualenvwrapper`` to easily create and enable
virtual environments using ``mkvirtualenv`` and ``workon``:

.. code-block:: shell

    sudo dnf install python3-virtualenvwrapper

If ``python3-virtualenvwrapper`` package is not available for your
system you can install it via ``pip``:

.. code-block:: shell

    pip install virtualenvwrapper --user # use pip3 in case of CentOS Stream 8

Note that if you have freshly installed the package you need to
open a new shell session to enable the wrapper functions. In case
you installed package via ``pip``, you need to source
``virtualenvwrapper.sh`` script. You can also consider adding
following lines into your ``.bash_profile``:

.. code-block:: shell

    source ${HOME}/.local/bin/virtualenvwrapper.sh

There is no default ``python`` in ``$PATH`` in case of CentOS Stream 8,
which causes sourcing of ``virtualenvwrapper.sh`` script to fail.
You can resolve it using ``alternatives``:

.. code-block:: shell

    alternatives --set python /usr/bin/python3

Now let's create a new virtual environment and install ``tmt`` in
editable mode there:

.. code-block:: shell

    mkvirtualenv tmt
    git clone https://github.com/teemtee/tmt
    cd tmt
    pip install -e .

The main ``tmt`` package contains only the core dependencies. For
building documentation, testing changes, importing/exporting test
cases or advanced provisioning options install the extra deps:

.. code-block:: shell

    pip install -e '.[docs]'
    pip install -e '.[tests]'
    pip install -e '.[convert]'
    pip install -e '.[provision]'

Or simply install all extra dependencies to make sure you have
everything needed for the tmt development ready on your system:

.. code-block:: shell

    pip install -e '.[all]'

Install the ``pre-commit`` package to run all available checks for
your commits to the project:

.. code-block:: shell

    sudo dnf install pre-commit # for Fedora
    pip install pre-commit --user # for CentOS Stream

Then you can install the hooks it via:

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

Build the rpms and execute the whole test coverage, including
tests which need the full virtualization support:

.. code-block:: shell

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

To run unit tests using pytest and generate coverage report:

.. code-block:: shell

    coverage run --source=tmt -m py.test tests
    coverage report

Install pytest and coverage using dnf:

.. code-block:: shell

    dnf install python3-pytest python3-coverage

or pip:

.. code-block:: shell

    # sudo required if not in a virtualenv
    pip install pytest coveralls

.. note::

   When adding new unit tests, do not create class-based tests derived from
   ``unittest.TestCase`` class. Such classes do not play well with Pytest's
   fixtures, see https://docs.pytest.org/en/7.1.x/how-to/unittest.html for
   details.

.. note::

   Tests which try various provision methods should use ``PROVISION_METHODS``
   environment variable to select which provision methods they can utilize
   during their execution. This variable is likely to have default ``container``
   or ``local`` and use ``adjust`` rule for ``how=full`` to add ``virtual`` method.

Docs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When submitting a change affecting user experience it's always
good to include respective documentation. You can add or update
the :ref:`specification`, extend the :ref:`examples` or write a
new chapter for the user :ref:`guide`.

For building documentation locally install necessary modules:

.. code-block:: shell

    pip install sphinx sphinx_rtd_theme

Make sure docutils are installed in order to build man pages:

.. code-block:: shell

    dnf install python3-docutils

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

Consider pasting the following checklist (or selected items which
are applicable) to the pull request description to easily track
progress of the implementation and prevent forgetting about
essential steps to be completed before it is merged:

.. code-block:: markdown

    * [ ] implement the feature
    * [ ] write documentation
    * [ ] extend the test coverage
    * [ ] update specification
    * [ ] adjust module docs
    * [ ] add a usage example
    * [ ] modify json schema
    * [ ] mention version

The version should be mentioned in the specification when a new
essential feature is added so that users can easily check whether
given functionality is already available in their package:

.. code-block:: rst

    .. versionadded:: 1.23

If the pull request addresses an existing issue, mention it using
one of the automatically parsed formats so that it is linked to
it, for example:

.. code-block:: markdown

    Fix #1234.


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
* Update ``README`` with new contributors since the last release
* Add a ``Release tmt-x.y.0`` commit with the specfile update
* Create a pull request with the commit, ensure tests pass, merge it

Release a new package to Fedora and EPEL repositories:

* Move the ``fedora`` branch to point to the new release
* Tag the commit with ``x.y.0``, push tags ``git push --tags``
* Create a source tarball using the ``make tarball`` command
* Draft a new `github release`__ based on the tag above
* Upload tarball to the release attachments and publish it
* Check Fedora `pull requests`__, make sure tests pass and merge

Finally, if everything went well:

* Close the corresponding release milestone
* Once the `copr build`__ is completed, move the ``quay`` branch
  to point to the release commit as well to build fresh container
  images.

Handle manually what did not went well:

* If the automation triggered by publishing the new github release
  was not successful, publish the fresh code to the `pypi`__
  repository manually using ``make wheel && make upload``
* If there was a problem with creating Fedora pull requests, you
  can trigger them manually using ``/packit propose-downstream``
  in any open issue.
* If running `packit propose-downstream`__ from your laptop make
  sure that the ``post-upstream-clone`` action is disabled in
  ``.packit.yaml`` to prevent bumping the devel version.

__ https://github.com/teemtee/tmt/releases/
__ https://src.fedoraproject.org/rpms/tmt/pull-requests
__ https://copr.fedorainfracloud.org/coprs/psss/tmt/builds/
__ https://pypi.org/project/tmt/
__ https://packit.dev/docs/cli/propose-downstream/
