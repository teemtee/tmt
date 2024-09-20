.. _releases:

======================
    Releases
======================

tmt-1.37.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :ref:`/plugins/report/junit` report plugin now validates all the XML
flavors against their respective XSD schemas and tries to prettify the final
XML output. These functionalities are always disabled for ``custom`` flavors.
The prettify functionality can be controlled for non-custom templates by
``--prettify`` and ``--no-prettify`` arguments.

The :ref:`/plugins/report/junit` report plugin now uses Jinja instead of
``junit-xml`` library to generate the JUnit XMLs. It also adds support for a
new ``--flavor`` argument. Using this argument the user can choose between a
``default`` flavor, which keeps the current behavior untouched, and a
``custom`` flavor where user must provide a custom template using a
``--template-path`` argument.

The ``fmf-id.ref`` will now try to report the most human-readable committish
reference, either branch, tag, git-describe, or if all fails the commit hash.
You may encounter this in the verbose log of ``tmt tests show`` or plan/test
imports.

In verbose mode, the ``discover`` step now prints information
about the beakerlib libraries which were fetched for the test
execution. Use ``tmt run discover -vvv`` to see the details.


tmt-1.36.1
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

tmt will now put SSH master control socket into ``ssh-socket``
subdirectory of a workdir. Originally, sockets were stored in
``/run/user/$UID`` directory, but this path led to conflicts when
multiple tmt instances shared sockets incorrectly. A fix landed in
1.36 that put sockets into ``provision`` subdirectory of each plan,
but this solution will break for plans with longer names because of
unavoidable UNIX socket path limit of 104 (or 108) characters.


tmt-1.36.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

tmt will now emit a warning when :ref:`custom test results</spec/tests/result>`
file does not follow the :ref:`result specification</spec/plans/results>`.

We have started to use ``warnings.deprecated`` to advertise upcoming
API deprecations.

The :ref:`/plugins/provision/beaker` provision plugin gains
support for submitting jobs on behalf of other users, through
``beaker-job-owner`` key. The current user must be a submission delegate
for the given job owner.

In preparation for subresults: subresults and their checks have been integrated
into HTML report and display plugin, result phase renamed to subresult.


tmt-1.35.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If during test execution guest freezes in the middle of reboot,
test results are now correctly stored, all test artifacts from
the ``TMT_TEST_DATA`` and ``TMT_PLAN_DATA`` directories should be
fetched and available for investigation in the report.

New best practices in the :ref:`docs` section now provide many
useful hints how to write good documentation when contributing
code.

The new key ``include-output-log`` and corresponding command line
options ``--include-output-log`` and ``--no-include-output-log``
can now be used in the :ref:`/plugins/report/junit` and
:ref:`/plugins/report/polarion` plugins to select whether only
failures or the full standard output should be included in the
generated report.

Change of Polarion field to store tmt id. Now using 'tmt ID' field,
specifically created for this purpose instead of 'Test Case ID' field.

The :ref:`/plugins/provision/beaker` provision plugin gains
support for :ref:`cpu.vendor-name</spec/hardware/cpu>` and
:ref:`beaker.pool</spec/hardware/beaker>` hardware requirements.

The linting of tests, plans and stories has been extended by detecting
duplicate ids.

Test directories pruning now works correctly for nested fmf trees
and there is also a test for it.

The test key :ref:`/spec/tests/result` now supports new value
``restraint`` which allows to treat each execution of the
``tmt-report-result``, ``rstrnt-report-result`` and
``rhts-report-result`` commands as an independent test for which a
separate result is reported. The behaviour for existing tests
which already utilise these commands remains unchanged (the
overall result is determined by selecting the result with the
value which resides highest on the hierarchy of `skip`, `pass`,
`warn`, `fail`).

Add support for ``--last``, ``--id``, and ``--skip`` params for
the ``clean`` subcommand. Users can clean resources from the last
run or from a run with a given id. Users can also choose to skip
cleaning ``guests``, ``runs`` or ``images``.


tmt-1.34.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :ref:`/spec/tests/duration` now supports multiplication.

Added option ``--failed-only`` to the ``tmt run tests`` subcommand,
enabling rerunning failed tests from previous runs.

The :ref:`/plugins/report/reportportal` plugin copies
launch description also into the suite description when the
``--suite-per-plan`` option is used.

The :ref:`virtual</plugins/provision/virtual.testcloud>` provision
plugin gains support for adding multiple disks to guests, by adding
the corresponding ``disk[N].size``
:ref:`HW requirements</spec/hardware/disk>`.


tmt-1.33.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :ref:`/plugins/provision/beaker` provision plugin gains
support for :ref:`cpu.cores</spec/hardware/cpu>` and
:ref:`virtualization.hypervisor</spec/hardware/virtualization>`
hardware requirements.

It is now possible to set SSH options for all connections spawned by tmt
by setting environment variables ``TMT_SSH_*``. This complements the
existing way of setting guest-specific SSH options by ``ssh-options`` key
of the guest. See :ref:`command-variables` for details.

New section :ref:`review` describing benefits and various forms of
pull request reviews has been added to the :ref:`contribute` docs.

The :ref:`dmesg test check</plugins/test-checks/dmesg>` can be
configured to look for custom patterns in the output of ``dmesg``
command, by setting its ``failure-pattern`` key.

Tests can now define their exit codes that would cause the test to be
restarted. Besides the ``TMT_REBOOT_COUNT`` environment variable, tmt
now exposes new variable called ``TMT_TEST_RESTART_COUNT`` to track
restarts of a said test. See :ref:`/spec/tests/restart` for details.

Requirements of the :ref:`/plugins/execute/upgrade` execute
plugin tasks are now correctly installed before the upgrade is
performed on the guest.


tmt-1.32.2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set priorities for package manager discovery. They are now probed
in order: ``rpm-ostree``, ``dnf5``, ``dnf``, ``yum``, ``apk``, ``apt``.
This order picks the right package manager in the case when the
guest is ``ostree-booted`` but has the dnf installed.


tmt-1.32.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The hardware specification for :ref:`/spec/hardware/disk` has been
extended with the new keys ``driver`` and ``model-name``. Users
can provision Beaker guests with a given disk model or driver using
the :ref:`/plugins/provision/beaker` provision plugin.

The :ref:`virtual</plugins/provision/virtual.testcloud>` provision plugin
gains support for :ref:`TPM hardware requirement</spec/hardware/tpm>`.
It is limited to TPM 2.0 for now, the future release of `testcloud`__,
the library behind ``virtual`` plugin, will extend the support to more
versions.

A new :ref:`watchdog test check</plugins/test-checks/watchdog>` has been
added. It monitors a guest running the test with either ping or SSH
connections, and may force reboot of the guest when it becomes
unresponsive. This is the first step towards helping tests handle kernel
panics and similar situations.

Internal implementation of basic package manager actions has been
refactored. tmt now supports package implementations to be shipped as
plugins, therefore allowing for tmt to work natively with distributions
beyond the ecosystem of rpm-based distributions. As a preview, ``apt``,
the package manager used by Debian and Ubuntu, ``rpm-ostree``, the
package manager used by ``rpm-ostree``-based Linux systems and ``apk``,
the package manager of Alpine Linux have been included in this release.

New environment variable ``TMT_TEST_ITERATION_ID`` has been added to
:ref:`test-variables`. This variable is a combination of a unique
run ID and the test serial number. The value is different for each
new test execution.

New environment variable ``TMT_REPORT_ARTIFACTS_URL`` has been added
to :ref:`command-variables`. It can be used to provide a link for
detailed test artifacts for report plugins to pick.

:ref:`Beaker</plugins/provision/beaker>` provision plugin gains
support for :ref:`System z cryptographic adapter</spec/hardware/zcrypt>`
HW requirement.

The :ref:`/spec/plans/discover/dist-git-source` apply patches now using
``rpmbuild -bp`` command. This is done on provisioned guest during
the ``prepare`` step, before required packages are installed.
It is possible to install build requires automatically with
``dist-git-install-builddeps`` flag or specify additional
packages required to be present with ``dist-git-require`` option.

__ https://pagure.io/testcloud/


tmt-1.31.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :ref:`/spec/plans/provision` step is now able to perform
**provisioning of multiple guests in parallel**. This can
considerably shorten the time needed for guest provisioning in
multihost plans. However, whether the parallel provisioning would
take place depends on what provision plugins were involved,
because not all plugins are compatible with this feature yet. As
of now, only :ref:`/plugins/provision/artemis`,
:ref:`/plugins/provision/connect`,
:ref:`/plugins/provision/container`,
:ref:`/plugins/provision/local`, and
:ref:`virtual</plugins/provision/virtual.testcloud>` are supported. All
other plugins would gracefully fall back to the pre-1.31 behavior,
provisioning in sequence.

The :ref:`/spec/plans/prepare` step now installs test requirements
only on guests on which the said tests would run. Tests can be
directed to subset of guests with a
:ref:`/spec/plans/discover/where` key, but, until 1.31, tmt would
install all requirements of a given test on all guests, even on
those on which the said test would never run.  This approach
consumed resources needlessly and might be a issue for tests with
conflicting requirements. Since 1.31, handling of
:ref:`/spec/tests/require` and :ref:`/spec/tests/recommend`
affects only guests the test would be scheduled on.

New option ``--again`` can be used to execute an already completed
step once again without completely removing the step workdir which
is done when ``--force`` is used.

New environment variable ``TMT_REBOOT_TIMEOUT`` has been added to
:ref:`command-variables`. It can be used to set a custom reboot
timeout. The default timeout was increased to 10 minutes.

New hardware specification key :ref:`/spec/hardware/zcrypt` has
been defined. It will be used for selecting guests with the given
`System z cryptographic adapter`.

A prepare step plugin :ref:`/plugins/prepare/feature` has been
implemented. As the first supported feature, ``epel`` repositories
can now be enabled using a concise configuration.

The report plugin :ref:`/spec/plans/report` has received new options.
Namely option ``--launch-per-plan`` for creating a new launch per each
plan, option ``--suite-per-plan`` for mapping a suite per each plan,
all enclosed in one launch (launch uuid is stored in run of the first
plan), option ``--launch-description`` for providing unified launch
description, intended mainly for suite-per-plan mapping, option
``--upload-to-launch LAUNCH_ID`` to append new plans to an existing
launch, option ``--upload-to-suite SUITE_ID`` to append new tests
to an existing suite within launch, option ``--launch-rerun`` for
reruns with 'Retry' item in RP, and option ``--defect-type`` for
passing the defect type to failing tests, enables report idle tests
to be additionally updated. Environment variables were rewritten to
the uniform form ``TMT_PLUGIN_REPORT_REPORTPORTAL_${option}``.


tmt-1.30.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The new :ref:`tmt try</stories/cli/try>` command provides an
interactive session which allows to easily run tests and
experiment with the provisioned guest. The functionality might
still change. This is the very first proof of concept included in
the release as a **tech preview** to gather early feedback and
finalize the outlined design. Give it a :ref:`/stories/cli/try`
and let us know what you think! :)

Now it's possible to use :ref:`custom_templates` when creating new
tests, plans and stories. In this way you can substantially speed
up the initial phase of the test creation by easily applying test
metadata and test script skeletons tailored to your individual
needs.

The :ref:`/spec/core/contact` key has been moved from the
:ref:`/spec/tests` specification to the :ref:`/spec/core`
attributes so now it can be used with plans and stories as well.

The :ref:`/plugins/provision/container` provision plugin
enables a network accessible to all containers in the plan. So for
faster :ref:`multihost-testing` it's now possible to use
containers as well.

For the purpose of tmt exit code, ``info`` test results are no
longer considered as failures, and therefore the exit code of tmt
changes. ``info`` results are now treated as ``pass`` results, and
would be counted towards the successful exit code, ``0``, instead
of the exit code ``2`` in older releases.

The :ref:`/spec/plans/report/polarion` report now supports the
``fips`` field to store information about whether the FIPS mode
was enabled or disabled on the guest during the test execution.

The ``name`` field of the :ref:`/spec/tests/check` specification
has been renamed to ``how``, to be more aligned with how plugins
are selected for step phases and export formats.

A new :ref:`/spec/tests/tty` boolean attribute was added to the
:ref:`/spec/tests` specification. Tests can now control if they
want to keep tty enabled. The default value of the attribute is
``false``, in sync with the previous default behaviour.

See the `full changelog`__ for more details.

__ https://github.com/teemtee/tmt/releases/tag/1.30.0


tmt-1.29.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Test directories can be pruned with the ``prune`` option usable in
the :ref:`/plugins/discover/fmf` plugin. When enabled, only
test's path and required files will be kept.

The :ref:`/spec/plans/discover/dist-git-source` option
``download-only`` skips extraction of downloaded sources. All
source files are now downloaded regardless this option.

Environment variables can now be also stored into the
``TMT_PLAN_ENVIRONMENT_FILE``. Variables defined in this file are
sourced immediately after the ``prepare`` step, making them
accessible in the tests and across all subsequent steps. See
the :ref:`step-variables` section for details.

When the ``tmt-report-result`` command is used it sets the test
result exclusively. The framework is not consulted any more. This
means that the test script exit code does not have any effect on
the test result. See also :ref:`/stories/features/report-result`.

The ``tmt-reboot`` command is now usable outside of the test
process. See the :ref:`/stories/features/reboot` section for usage
details.

The :ref:`/spec/plans/provision` step methods gain the ``become``
option which allows to use a user account and execute
``prepare``, ``execute`` and ``finish`` steps using ``sudo -E``
when necessary.

The :ref:`/spec/plans/report/html` report plugin now shows
:ref:`/spec/tests/check` results so that it's possible to inspect
detected AVC denials directly from the report.

See the `full changelog`__ for more details.

__ https://github.com/teemtee/tmt/releases/tag/1.29.0


tmt-1.28.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The new :ref:`/stories/cli/multiple phases/update-missing` option
can be used to update step phase fields only when not set in the
``fmf`` files. In this way it's possible to easily fill the gaps
in the plans, for example provide the default distro image.

The :ref:`/spec/plans/report/html` report plugin now shows
provided :ref:`/spec/plans/context` and link to the test ``data``
directory so that additional logs can be easily checked.

The **avc** :ref:`/spec/tests/check` allows to detect avc denials
which appear during the test execution.

A new ``skip`` custom result outcome has been added to the
:ref:`/spec/plans/results` specification.

All context :ref:`/spec/context/dimension` values are now handled
in a case insensitive way.

See the `full changelog`__ for more details.

__ https://github.com/teemtee/tmt/releases/tag/1.28.0
