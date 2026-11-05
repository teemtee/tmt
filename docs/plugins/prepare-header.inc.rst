The ``prepare`` step is used to define how the guest
environment should be prepared so that the tests can be
successfully executed.

The :ref:`/plugins/prepare/install` plugin provides an easy
way to install required or recommended packages from disk and
from the official distribution or copr repositories. Use the
:ref:`/plugins/prepare/ansible` plugin for applying custom
playbooks or execute :ref:`/plugins/prepare/shell` scripts
to perform arbitrary preparation tasks.

See the :ref:`/plugins/prepare` section for the full list of
available prepare plugins and their supported options.

.. code-block:: yaml

    # Install fresh packages from a custom copr repository
    prepare:
      - how: install
        copr: psss/tmt
        package: tmt+all

.. code-block:: yaml

    # Install required packages and start the service
    prepare:
      - name: packages
        how: install
        package: [httpd, curl]
      - name: service
        how: shell
        script: systemctl start httpd

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

     Individual plugins may define their own special ``order`` values,
     and you shall find the relevant information in :ref:`plugins`
     documentation.

.. note::

    If you want to use the ``prepare`` step to generate data
    files needed for testing during the ``execute`` step,
    move or copy them into ``${TMT_PLAN_DATA}`` directory. Only
    files in this directory are guaranteed to be preserved.

.. _/plugins/prepare/where:

where
-----

.. Preserve the original story targets for existing cross-references.

.. tmt:story:: /spec/plans/prepare/where
    :title: where

    Apply preparation on selected guests

    In the :tmt:story:`/spec/plans/provision/multihost` scenarios it
    is often necessary to perform different preparation tasks on
    individual guests. The ``where`` key allows to select guests
    where the preparation should be applied by providing their
    ``name`` or the ``role`` they play in the scenario. Use a
    list to specify multiple names or roles. By default, when
    the ``where`` key is not defined, preparation is done on all
    provisioned guests.

    .. code-block:: yaml

        # Start Apache on the server
        prepare:
          - how: shell
            script: systemctl start httpd
            where: server

        # Apply common setup on the primary server and all replicas
        prepare:
          - how: ansible
            playbook: common.yaml
            where: [primary, replica]

.. _/plugins/prepare/when:

when
----

.. tmt:story:: /spec/plans/prepare/when
    :title: when

    Conditional step configuration

    Using the ``when`` key makes it easier to restrict a step configuration
    to run only if any of the specified rules matches.
    The syntax is the same as in ``adjust`` and :tmt:story:`/spec/context`.

    Values can be single string with the rule or list of rules.

    .. code-block:: yaml

        prepare:
          - name: Prepare config to run only on Fedora
            when: distro == fedora
            how: shell
            script: ./fedora_specific.
          - name: Runs always
            how: shell
            script: ./setup.sh
          - name: Just a demo of more rules in the 'when' key
            how: shell
            script: ./something.sh
            when:
            - initiator == konflux and distro == fedora
            - initiator == human and distro == fedora
