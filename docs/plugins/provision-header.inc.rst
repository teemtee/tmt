Describes what environment is needed for testing and how it should be
provisioned. There are several provision plugins supporting multiple ways
to provision the environment for testing, for example:

* :ref:`/plugins/provision/virtual.testcloud`
* :ref:`/plugins/provision/container`
* :ref:`/plugins/provision/connect`
* :ref:`/plugins/provision/local`
* :ref:`/plugins/provision/artemis`

.. _/plugins/provision/hard-reboot:

Hard reboot
-----------

Hard reboot is not yet supported by all ``provision`` plugins, and
therefore the following features may not work with plugins that
lack the capability:

* :ref:`restart-with-reboot</spec/tests/restart>` test key
* :ref:`reboot</plugins/test-checks/watchdog>` action of the ``watchdog`` test check

Following plugins fully implement hard reboot:

* :ref:`/plugins/provision/connect` (Only when ``hard-reboot`` key is defined)
* :ref:`/plugins/provision/beaker`
* :ref:`/plugins/provision/container`
* :ref:`virtual</plugins/provision/virtual.testcloud>`
* :ref:`/plugins/provision/artemis`

.. include:: hardware-matrix.rst


.. _/plugins/provision/ssh-options:

SSH options
-----------

When communicating with guests over SSH, tmt adds several SSH options by
default to relevant commands:

.. code-block::

    # Try establishing connection multiple times before giving up.
    ConnectionAttempts=5
    ConnectTimeout=60

    # Prevent SSH from disconnecting if no data has been
    # received from the server for a long time.
    ServerAliveInterval=5
    ServerAliveCountMax=60

Additional SSH options can be specified either via ``ssh-option`` key
of respective plugins, or by setting ``TMT_SSH_*`` environment
variables; see :ref:`command-variables` for details.
