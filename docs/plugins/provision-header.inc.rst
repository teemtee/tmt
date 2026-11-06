Describes what environment is needed for testing and how it should be
provisioned. There are several provision plugins supporting multiple ways
to provision the environment for testing, for example:

* :ref:`/plugins/provision/virtual.testcloud`
* :ref:`/plugins/provision/container`
* :ref:`/plugins/provision/connect`
* :ref:`/plugins/provision/local`
* :ref:`/plugins/provision/artemis`

As part of the provision step it is also possible to specify
detailed hardware requirements for the testing environment. See
the :tmt:story:`/spec/hardware` specification section for details.


.. _/plugins/provision/multihost:

Multihost
---------

.. Preserve the original story targets for existing cross-references.

.. tmt:story:: /spec/plans/provision/multihost
    :title: multihost

    Multihost testing specification

    .. versionchanged:: 1.24

    As a part of the provision step it is possible to request
    multiple guests to be provisioned for testing. Each guest
    has to be assigned a unique ``name`` which is used to
    identify it.

    The optional parameter ``role`` can be used to mark
    related guests so that common actions can be applied to
    all such guests at once. An example role name can be
    `client` or `server` but arbitrary identifier can be used.

    Both `name` and `role` can be used together with the
    ``where`` key to select guests on which the
    :tmt:story:`preparation</spec/plans/prepare/where>`
    tasks should be applied or where the test
    :tmt:story:`execution</spec/plans/discover/where>` should
    take place.

    See :tmt:story:`/spec/plans/guest-topology` for details on how
    this information is exposed to tests and ``prepare`` and
    ``finish`` tasks.

    .. code-block:: yaml

        # Request two guests
        provision:
          - name: server
            how: virtual
          - name: client
            how: virtual

        # Assign role to guests
        provision:
          - name: main-server
            role: primary
          - name: backup-one
            role: replica
          - name: backup-two
            role: replica
          - name: tester-one
            role: client
          - name: tester-two
            role: client

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

.. _/plugins/provision/kickstart:

Kickstart
---------

.. tmt:story:: /spec/plans/provision/kickstart
    :title: kickstart

    As part of the :tmt:story:`/spec/plans/provision` step it is possible to
    use the ``kickstart`` key to specify additional requirements for the
    installation of a guest. It is possible to specify a kickstart
    script that will for example specify specific partitioning.

    The structure of a kickstart file is separated into several
    sections.

    pre-install
        Corresponds to the ``%pre`` section of a file.  It can contain
        ``bash`` commands, this part is run before the installation of a
        guest.

    post-install
        Corresponds to the ``%post`` section of a file.  It can contain
        ``bash`` commands, this part is run after the installation of a
        guest.

    script
        Contains the kickstart specific commands that are run during the
        installation of a guest.

    It is also possible to specify ``metadata``. This part may be
    interpreted differently for each of the pools that the guest is
    created from. For example, in Beaker this section can be used to
    modify the default kickstart template used by Beaker.  Similarly
    works the ``kernel-options`` and ``kernel-options-post``.  Kernel
    options are passed on the kernel command line when the installer is
    booted.  Post-install kernel options are set in the boot loader
    configuration, to be passed on the kernel command line after
    installation.

    .. note::

        The implementation for the ``kickstart`` key is in progress.
        Support of a kickstart file is currently limited to Beaker
        provisioning, as implemented by tmt's beaker and artemis
        plugins, and may not be fully supported by other provisioning
        plugins in the future.  Check individual plugin documentation
        for additional information on the kickstart support.

    .. code-block:: yaml

        # Use the artemis plugin to provision a guest from Beaker.
        # The following `kickstart` specification will be run
        # during the guest installation.
        provision:
            how: artemis
            pool: beaker
            image: rhel-7
            kickstart:
                pre-install: |
                    %pre --log=/dev/console
                    disk=$(lsblk | grep disk | awk '{print $1}')
                    echo $disk
                    %end
                script: |
                    lang en_US.UTF-8
                    zerombr
                    clearpart --all --initlabel
                    part /boot --fstype="xfs" --size=200
                    part swap --fstype="swap" --size=4096
                    part / --fstype="xfs" --size=10000 --grow
                post-install: |
                    %post
                    systemctl disable firewalld
                    %end
                metadata: "no_autopart harness=restraint"
                kernel-options: "ksdevice=eth1"
                kernel-options-post: "quiet"

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
