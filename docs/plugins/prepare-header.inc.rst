The :tmt:story:`/spec/plans/prepare` step is used to define how the guest
environment should be prepared so that the tests can be
successfully executed.

The :ref:`/plugins/prepare/install` plugin installs packages from enabled
repositories, copr repositories, local RPM files or remote RPM URLs. Use the
:ref:`/plugins/prepare/ansible` plugin for applying custom
playbooks or execute :ref:`/plugins/prepare/shell` scripts
to perform arbitrary preparation tasks.

The :ref:`/plugins/prepare/artifact` plugin makes specific build artifacts
available on the guest for installation. Use the
:ref:`/plugins/prepare/feature` plugin to enable or disable common
features such as EPEL repositories or FIPS mode. The
:ref:`/plugins/prepare/verify-installation` plugin checks that installed
packages came from the expected repositories.

The default method is :ref:`shell </plugins/prepare/shell>`.

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
