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

.. include:: hardware-matrix.rst
