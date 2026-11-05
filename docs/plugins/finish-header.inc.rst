The :tmt:story:`/spec/plans/finish` step plugins implement actions to be
performed after the test execution has been completed. These can
be useful for finishing tasks such as an additional guest cleanup
or uploading specific logs to an external server.

.. _/plugins/finish/where:

where
-----

.. Preserve the original story targets for existing cross-references.

.. tmt:story:: /spec/plans/finish/where
    :title: where

    Perform finishing tasks on selected guests

    In the :tmt:story:`/spec/plans/provision/multihost` scenarios it
    is often necessary to perform different completion tasks
    on individual guests. The ``where`` key allows to select
    guests where the finishing tasks should be applied by
    providing their ``name`` or the ``role`` they play in the
    scenario. Use a list to specify multiple names or roles.
    By default, when the ``where`` key is not defined,
    finishing tasks are performed on all provisioned guests.

    .. code-block:: yaml

        # Stop Apache on the server
        finish:
          - how: shell
            script: systemctl stop httpd
            where: server

.. _/plugins/finish/when:

when
----

.. tmt:story:: /spec/plans/finish/when
    :title: when

    Conditional step configuration

    Using the ``when`` key makes it easier to restrict a step configuration
    to run only if any of the specified rules matches.
    The syntax is the same as in ``adjust`` and :tmt:story:`/spec/context`.

    Values can be single string with the rule or list of rules.

    .. code-block:: yaml

        finish:
          - name: finish config to run only on Fedora
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
