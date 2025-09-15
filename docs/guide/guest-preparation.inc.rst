.. _guest-preparation:

Guest Preparation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There are several requirements which need to be satisfied in order
to successfully execute tests on guests. To make sure everything
needed is ready ``tmt`` expects one of the following three
scenarios:

1. root account is used on the guest so that any missing packages
   can be installed and additional scripts can be copied to
   directories with limited access
2. password-less ``sudo`` command is provided so that the
   above-mentioned actions which need superuser permissions can be
   executed with it
3. all the guest requirements are set up and in place, prepared by
   the user, so that no additional actions need to be performed

If you choose option 3 above, please review carefully the detailed
requirements described below and adjust your guest preparation
scripts (e.g. Containerfile used for creating the guest image) to
ensure your tests can be executed smoothly.

.. _minimal-requirements:

Minimal Requirements
------------------------------------------------------------------

For executing shell scripts ``bash`` is required to be installed
as it is used by the prepare :ref:`/plugins/prepare/shell` and
finish :ref:`/plugins/finish/shell` plugins as well as for test
execution itself.

For correctly handling locking of important files ``flock`` is
needed.

.. _helper-scripts:

Helper Scripts
------------------------------------------------------------------

On the provisioned guests ``tmt`` installs several helper scripts
which can be used by tests for special actions:

* :ref:`/stories/features/reboot` using ``tmt-reboot``
* :ref:`/stories/features/abort`  using ``tmt-abort``
* :ref:`/stories/features/report-log` using ``tmt-file-submit``
* :ref:`/stories/features/report-result` using ``tmt-report-result``

By default these are installed under ``/usr/local/bin``, use
``TMT_SCRIPTS_DIR`` environment variable to choose a different
scripts path. See also :ref:`restraint-compatibility` for
alternative script aliases which can be used as well.
