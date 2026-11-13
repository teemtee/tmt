The :tmt:story:`/spec/plans/provision` step describes what environment is
needed for testing and how it should be provisioned. There are several
provision plugins supporting multiple ways to provision the environment for
testing, for example:

* :ref:`/plugins/provision/virtual.testcloud`
* :ref:`/plugins/provision/container`
* :ref:`/plugins/provision/connect`
* :ref:`/plugins/provision/local`
* :ref:`/plugins/provision/artemis`

As part of the provision step it is also possible to specify
detailed hardware requirements for the testing environment. See
the :tmt:story:`/spec/hardware` specification section for details.


.. _/plugins/provision/ansible:

Ansible
-------

.. tmt:story:: /spec/plans/provision/ansible
    :title: ansible

    Per-guest Ansible customization

    Each provisioned guest may define an optional ``ansible`` key
    to define its corresponding Ansible inventory section.

    group
        Assigns the guest to an Ansible specific group. If omitted,
        the :ref:`role </plugins/provision/common-keys>` key would
        serve as the Ansible group name. If neither ``ansible.group``
        nor ``role`` is set, the host will be placed in
        the `ungrouped` group.

    vars
        Defines host-specific Ansible variables to include under
        that host in the inventory.

    .. versionadded:: 1.60

    .. code-block:: yaml

        # Plan file
        provision:
            # If both role and ansible.group are set,
            # ansible.group takes precedence
          - name: master-guest
            role: master
            ansible:
                group: server
                vars:
                    var1: value1
                    var2: value2
          - name: client-guest
            role: client
            ansible:
                vars:
                    ansible_user: fedora
                    ansible_port: 2222
            # If a specified group doesn't exist in the layout,
            # it will be created automatically in the output inventory.
          - name: database-guest
            role: database
            # Orphan guest without role or ansible.group,
            # will be placed in `ungrouped`
          - name: orphan-guest

        # Generated inventory file
        all:
            children:
                server:
                    hosts:
                        master-guest: {}
                client:
                    hosts:
                        client-guest: {}
                database:
                    hosts:
                        database-guest: {}
                ungrouped:
                    hosts:
                        orphan-guest: {}
            hosts:
                master-guest:
                    var1: value1
                    var2: value2
                client-guest:
                    ansible_user: fedora
                    ansible_port: 2222
                database-guest: {}
                orphan-guest: {}

.. _/plugins/provision/hard-reboot:

Hard reboot
-----------

Hard reboot is not yet supported by all ``provision`` plugins, and
therefore the following features may not work with plugins that
lack the capability:

* :tmt:story:`restart-with-reboot</spec/tests/restart>` test key
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
