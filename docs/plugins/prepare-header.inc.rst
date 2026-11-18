The :tmt:story:`/spec/plans/prepare` step is used to define how the guest
environment should be prepared so that the tests can be
successfully executed.

The :ref:`/plugins/prepare/install` plugin provides an easy
way to install required or recommended packages from disk and
from the official distribution or copr repositories. Use the
:ref:`/plugins/prepare/ansible` plugin for applying custom
playbooks or execute :ref:`/plugins/prepare/shell` scripts
to perform arbitrary preparation tasks.

.. _/plugins/prepare/order:

Preparation order
-----------------

Use the ``order`` attribute to select in which order the
preparation should happen if there are multiple configs.
The following are predefined ``order`` values of various
preparations by tmt:

  30
      Installation of essential plugin requirements.

  50
      The default order of any object.

  70
      Installation of packages :tmt:story:`required</spec/tests/require>`
      by tests (including :tmt:story:`/spec/tests/framework` and
      :tmt:story:`/spec/tests/check` requires).

  75
      Installation of packages :tmt:story:`recommended</spec/tests/recommend>` by tests.

  79
      Verification of package source repositories after installation.

  .. note::

     Individual plugins may define their own special ``order`` values.

.. note::

    If you want to use the ``prepare`` step to generate data
    files needed for testing during the ``execute`` step,
    move or copy them into ``${TMT_PLAN_DATA}`` directory. Only
    files in this directory are guaranteed to be preserved.
