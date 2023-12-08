.. _releases:

======================
    Releases
======================

tmt-1.30
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
metadata and test script skeletons taylored to your individual
needs.

The :ref:`/spec/core/contact` key has been moved from the
:ref:`/spec/tests` specification to the :ref:`/spec/core`
attributes so now it can be used with plans and stories as well.

The :ref:`/spec/plans/provision/container` provision plugin
enables a network accessible to all containers in the plan. So for
faster :ref:`multihost-testing` it's now possible to use
containers as well.

For the purpose of tmt exit code, ``info`` test results are no
longer considered as failures, and therefore the exit code of tmt
changes. ``info`` results are now treated as ``pass`` results, and
would be counted towards the succesful exit code, ``0``, instead
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


tmt-1.29
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Test directories can be pruned with the ``prune`` option usable in
the :ref:`/spec/plans/discover/fmf` plugin. When enabled, only
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


tmt-1.28
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
