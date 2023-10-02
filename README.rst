.. _overview:

======================
    tmt
======================

Test Management Tool


Description
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``tmt`` tool provides a user-friendly way to work with tests.
You can comfortably create new tests, safely and easily run tests
across different environments, review test results, debug test
code and enable tests in the CI using a consistent and concise
config.

The python module and command-line tool implement the Metadata
Specification which allows storing all needed test execution data
directly within a git repository. Together with possibility to
reference remote repositories it makes it easy to share test
coverage across projects and distros.

The Flexible Metadata Format ``fmf`` is used to store data in both
human and machine readable way close to the source code. Thanks to
inheritance and elasticity metadata are organized in the structure
efficiently, preventing unnecessary duplication.


Specification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There are several metadata levels defined by the specification:

**Core** attributes such as `summary` or `description` which are
common across all levels are defined by the special L0 metadata.

**Tests**, or L1 metadata, define attributes which are closely
related to individual test cases such as `test` script,
`framework`, directory `path` where the test should be executed,
maximum test `duration` or packages required to run the test.

**Plans**, also called L2 metadata, are used to group relevant
tests and enable them in the CI. They describe how to `discover`
tests for execution, how to `provision` the environment, how to
`prepare` it for testing, how to `execute` tests and `report` test
results.

**Stories**, which implement the L3 metadata, can be used to track
implementation, test and documentation coverage for individual
features or requirements. Thanks to this you can track everything
in one place, including the project implementation progress.


Synopsis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Command line usage is straightforward::

    tmt command [options]


Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Let's see which tests, plans and stories are available::

    tmt

Initialize the metadata tree in the current directory, optionally
with example content based on templates::

    tmt init
    tmt init --template base

Run all or selected steps for each plan::

    tmt run
    tmt run discover
    tmt run prepare execute

List tests, show details, check against the specification::

    tmt tests ls
    tmt tests show
    tmt tests lint

Create a new test, import test metadata from other formats::

    tmt test create
    tmt test import

List plans, show details, check against the specification::

    tmt plans ls
    tmt plans show
    tmt plans lint

List stories, check details, show coverage status::

    tmt stories ls
    tmt stories show
    tmt stories coverage

Many commands support regular expression filtering and other
specific options::

    tmt stories ls cli
    tmt stories show create
    tmt stories coverage --implemented

Check help message of individual commands for the full list of
available options.


Options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here is the list of the most frequently used commands and options.

Run
---

The `run` command is used to execute test steps. By default all
test steps are run. See the L2 Metadata specification for detailed
description of individual steps. Here is a brief overview:

discover
    Gather information about test cases to be executed.

provision
    Provision an environment for testing or use localhost.

prepare
    Prepare the environment for testing.

execute
    Run tests using the specified executor.

report
    Provide test results overview and send reports.

finish
    Perform the finishing tasks and clean up provisioned guests.


Tests
-----

Manage tests (L1 metadata). Check available tests, inspect their
metadata, gather old metadata from various sources and stored them
in the new fmf format.

ls
    List available tests.
show
    Show test details.
lint
    Check tests against the L1 metadata specification.
create
    Create a new test based on given template.
import
    Convert old test metadata into the new fmf format.


Plans
-----

Manage test plans (L2 metadata). Search for available plans.
Explore detailed test step configuration.

ls
    List available plans.
show
    Show plan details.
lint
    Check plans against the L2 metadata specification.


Stories
-------

Manage user stories. Check available user stories. Explore
coverage (test, implementation, documentation).

ls
    List available stories.
show
    Show story details.
coverage
    Show code, test and docs coverage for given stories.
export
    Export selected stories into desired format.


Utils
-----

Various utility options.

--root PATH
    Path to the metadata tree, current directory used by default.

--verbose
    Print additional information.

--debug
    Turn on debugging output.

Check help message of individual commands for the full list of
available options.


.. _install:

Install
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The main ``tmt`` package provides the core features with a minimal
set of dependencies::

    sudo dnf install tmt

In order to enable additional functionality, such as particular
provision or report plugins, install the respective subpackage::

    sudo dnf install tmt+test-convert
    sudo dnf install tmt+provision-container
    sudo dnf install tmt+provision-virtual

If you don't care about disk space and want to have all available
features right at hand install everything::

    sudo dnf install tmt+all

For CentOS and RHEL, first make sure that you have available the
`EPEL <https://docs.fedoraproject.org/en-US/epel/>`_ repository.
You might also have to enable additional repositories::

    sudo dnf config-manager --enable crb         # CentOS 9
    sudo dnf config-manager --enable rhel-CRB    # RHEL 9
    sudo dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm

    sudo dnf install tmt

For plugins which cannot work outside of VPN and so live within
its walls you need to enable the internal copr repository first.
Then you can install either everything or only those you need::

    sudo dnf install tmt-redhat-all
    sudo dnf install tmt-redhat-*

Impatient to try the fresh features as soon as possible? Install
the latest greatest version from the ``copr`` repository::

    sudo dnf copr enable @teemtee/tmt
    sudo dnf install tmt

Not sure, just want to try out how it works? Experiment safely and
easily inside a container::

    podman run -it --rm quay.io/testing-farm/tmt bash
    podman run -it --rm quay.io/testing-farm/tmt-all bash

.. _pip_install:

When installing using ``pip`` you might need to install additional
packages on your system::

    sudo dnf install gcc redhat-rpm-config
    sudo dnf install {python3,libvirt,krb5,libpq}-devel
    pip install --user tmt

On other distributions than Fedora or RHEL the package names might
be different. For example on Ubuntu to install all packages to
have provision plugins working::

    sudo apt install libkrb5-dev pkg-config libvirt-dev genisoimage qemu-kvm libvirt-daemon-system
    pip install --user "tmt[provision]"

Note: You can omit the ``--user`` flag if in a virtual environment.


Shell Completion
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The rpm package includes a system wide script which enables the
command line completion for ``bash`` so no additional config
should be needed. If you use a different installation method or
prefer another shell, see the instructions below.

For Bash, add this to ``~/.bashrc``::

    eval "$(_TMT_COMPLETE=source_bash tmt)"

For Zsh, add this to ``~/.zshrc``::

    eval "$(_TMT_COMPLETE=source_zsh tmt)"

For Fish, add this to ``~/.config/fish/completions/tmt.fish``::

    eval (env _TMT_COMPLETE=source_fish tmt)

Open a new shell to enable completion. Or run the ``eval`` command
directly in your current shell to enable it temporarily.

This is however run every time you start a shell which can cause
some delay. To speed it up, write the generated script to a file
and then source it from your shell's configuration file. All
of this can be achieved using ``tmt setup completion`` command.
By default, it outputs the completion script to the terminal but
it can also add it to your ``~/.bashrc`` or ``~/.zshrc`` using
the ``--install`` option::

    tmt setup completion {bash, zsh, fish} --install


Exit Codes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following exit codes are returned from ``tmt run``. Note that
you can use the ``--quiet`` option to completely disable output
and only check for the exit code.

0
    At least one test passed, there was no fail, warn or error.
1
    There was a fail or warn identified, but no error.
2
    Errors occured during test execution.
3
    No test results found.


Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The list of available environment variables which can be used to
adjust the execution.


Command Variables
-----------------

The following environment variables can be used to modify
behaviour of the ``tmt`` command.

TMT_DEBUG
    Enable the desired debug level. Most of the commands support
    levels from 1 to 3. However, some of the plugins go even
    deeper when needed.

TMT_PLUGINS
    Path to a directory with additional plugins. Multiple paths
    separated with the ``:`` character can be provided as well.

TMT_WORKDIR_ROOT
    Path to root directory containing run workdirs. Defaults to
    ``/var/tmp/tmt``.

NO_COLOR, TMT_NO_COLOR
    Disable colors in the output, both the actual output and
    logging messages. Output only plain, non-colored text.

    Two variables are accepted, one with the usual ``TMT_``
    prefix, but tmt accepts also ``NO_COLOR`` to support the
    NO_COLOR effort, see https://no-color.org/ for more
    information.

TMT_FORCE_COLOR
    Enforce colors in the output, both the actual output and
    logging messages. Might come handy when tmt's output streams
    are not terminal-like, yet its output would be displayed by
    tools with ANSI color support. This is often the case of
    various CI systems.

    Note that ``TMT_FORCE_COLOR`` takes priority over ``NO_COLOR``
    and ``TMT_NO_COLOR``. If user tries both to disable and enable
    colorization, output would be colorized.

TMT_SHOW_TRACEBACK
    By default, when tmt reports an error, the corresponding
    traceback is not printed out. When ``TMT_SHOW_TRACEBACK`` is
    set to any string except ``0``, traceback would be printed out.

TMT_OUTPUT_WIDTH
    By default, the output width of commands like ``tmt * show`` is constrained
    to 79 characters. Set this variable to an integer to change the limit.

TMT_GIT_CREDENTIALS_URL_<suffix>, TMT_GIT_CREDENTIALS_VALUE_<suffix>
    Variable pairs used to provide credentials to clone git
    repositories. Suffix identifies the pair and determines the order in which URL regexp is tried.

    The ``TMT_GIT_CREDENTIALS_URL_<suffix>`` contains regexp to search against
    url to clone. For first successful search the content of the ``TMT_GIT_CREDENTIALS_VALUE_<suffix>``
    variable is used as the credential value. When it is set to an empty string, unmodified url is used.

    Example usage:

    `GitLab`__ credentials need to contain nonempty username followed by colon and token value::

        TMT_GIT_CREDENTIALS_URL_lab='gitlab.com/mysecretproject'
        TMT_GIT_CREDENTIALS_VALUE_lab='foo:secrettoken'

    `GitHub`__ credentials contain just the token value::

        TMT_GIT_CREDENTIALS_URL_hub='github.com/teemtee'
        TMT_GIT_CREDENTIALS_VALUE_hub='secrettoken'

__ https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html#clone-repository-using-personal-access-token
__ https://github.blog/2012-09-21-easier-builds-and-deployments-using-git-over-https-and-oauth/
.. versionadded:: 1.26

Step Variables
--------------

The following environment variables are provided to the environment
during ``prepare``, ``execute`` and ``finish`` steps:

TMT_TREE
    The full path of the working directory where the metadata tree
    is copied. This usually contains the whole git repository from
    which tests have been executed.

TMT_PLAN_DATA
    Path to the common directory used for storing logs and other
    artifacts related to the whole plan execution. It is pulled
    back from the guest and available for inspection after the
    plan is completed.

TMT_VERSION
    The version of tmt.

Test Variables
--------------

The following environment variables are provided to the test
during the execution:

TMT_TEST_NAME
    The test name, as a resolved FMF object name starting with ``/``
    from the root of the hierarchy.

TMT_TEST_DATA
    Path to the directory where test can store logs and other
    artifacts generated during its execution. These will be pulled
    back from the guest and available for inspection after the
    test execution is finished.

TMT_TEST_SERIAL_NUMBER
    The serial number of running test in the whole plan. Each test
    is assigned its own serial number.

TMT_TEST_METADATA
    Path to a YAML-formatted file with test metadata collected
    during the ``discover`` step.

TMT_SOURCE_DIR
    Path to directory with downloaded and extracted sources if
    the ``dist-git-source`` option was used in the ``discover``
    step.

TMT_REBOOT_COUNT
    During the test execution the ``tmt-reboot`` command can be
    used to request reboot of the guest. This variable contains
    number of reboots which already happened during the test.
    Value is set to ``0`` if no reboot occurred.

    In order to keep backward-compatibility with older tests,
    ``rhts-reboot`` and ``rstrnt-reboot`` commands are supported
    for requesting the reboot, variables ``REBOOTCOUNT`` and
    ``RSTRNT_REBOOTCOUNT`` contain number of reboots as well.

TMT_TOPOLOGY_BASH, TMT_TOPOLOGY_YAML
    Paths of files describing existing guests, their roles and the
    guest on which the test is running. Format of these files
    is described in the ``Guest Topology Format`` section of the
    plan specification.


Plugin Variables
----------------

Each plugin option can be also specified via environment variable.
Variables follow a naming scheme utilizing plugin name, step it
belongs to, and the option name:

    ``TMT_PLUGIN_${STEP}_${PLUGIN}_${OPTION}``

All values are upper-cased, with dashes (``-``) replaced by
underscores (``_``).

For example, an execute plugin "tmt" would run with verbosity
equal to ``-vvv``::

    TMT_PLUGIN_EXECUTE_TMT_VERBOSE=3 tmt run ... execute -h tmt ...

Command-line takes precedence over environment variables, therefore
``-v`` would undo the effect of environment variable, and reduce
verbosity to one level only::

    TMT_PLUGIN_EXECUTE_TMT_VERBOSE=3 tmt run ... execute -h tmt -v ...

Environment variables - just like command-line options - take
precedence over values stored in files. For example, consider the
following discover step::

    discover:
        how: fmf
        url: https://example.org/

The following commands would override the URL::

    tmt run ... discover -h fmf --url https://actual.org/ ...

    TMT_PLUGIN_DISCOVER_FMF_URL=https://actual.org/ tmt run ...

For setting flag-like option, 0 and 1 are the expected value. For
example, an interactive mode would be enabled in this run::

    TMT_PLUGIN_EXECUTE_TMT_INTERACTIVE=1 tmt run ... execute -h tmt ...

.. note::

   The following applies to situations when a plugin is specified
   on the command line only. Keys of plugins specified in fmf files
   would not be modified. This is a limit of the current implementation,
   and will be addressed in the future::

      # Here the verbosity will not be increased since the plugin is
      # not mentioned on the command line:
      $ TMT_PLUGIN_DISCOVER_FMF_VERBOSE=2 tmt run -a

      # Here the environment variable will take effect:
      $ TMT_PLUGIN_DISCOVER_FMF_VERBOSE=2 tmt run -a discover -h fmf ...


Links
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Git:
https://github.com/teemtee/tmt

Docs:
http://tmt.readthedocs.io/

Stories:
https://tmt.readthedocs.io/en/stable/stories.html

Issues:
https://github.com/teemtee/tmt/issues

Releases:
https://github.com/teemtee/tmt/releases

Copr:
https://copr.fedorainfracloud.org/coprs/g/teemtee/tmt/

PIP:
https://pypi.org/project/tmt/

Metadata Specification:
https://tmt.readthedocs.io/en/stable/spec.html

Flexible Metadata Format:
http://fmf.readthedocs.io/

Packit & Testing Farm:
https://packit.dev/testing-farm/


Authors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Petr Šplíchal, Miro Hrončok, Alexander Sosedkin, Lukáš Zachar,
Petr Menšík, Leoš Pol, Miroslav Vadkerti, Pavel Valena, Jakub
Heger, Honza Horák, Rachel Sibley, František Nečas, Michal
Ruprich, Martin Kyral, Miloš Prchlík, Tomáš Navrátil, František
Lachman, Patrik Kis, Ondrej Mosnáček, Andrea Ficková, Denis
Karpelevich, Michal Srb, Jan Ščotka, Artem Zhukov, Vinzenz
Feenstra, Inessa Vasilevskaya, Štěpán Němec, Robin Hack, Yulia
Kopkova, Ondrej Moriš, Martin Zelený, Karel Šrot, František
Zatloukal, Simon Walter, Petr Matyáš, Yariv Rachmani, Pavel
Cahyna, Martin Litwora, Brian Grech, Vojtěch Eichler, Philip Daly,
Vector Li, Evgeny Fedin, Guy Inger, Adrián Tomašov, Jan Havlín,
Lukáš Kotek, Daniel Diblík, Laura Barcziova, Marián Konček,
Marcin Sobczyk, Jiří Jabůrek, Huijing Hei, Tibor Dudlák, Jan
Macků, Filip Vágner, Martin Hoyer, Iveta Česalová, Yi Zhang,
Zhaojuan Guo, Natália Bubáková and Michal Josef Špaček.


Copyright
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Copyright Red Hat

This program is free software; you can redistribute it and/or
modify it under the terms of the MIT License.
