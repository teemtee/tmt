.. _/plugins/report/when:

when
----

.. Preserve the original story targets for existing cross-references.

.. tmt:story:: /spec/plans/report/when
    :title: when

    Conditional step configuration

    Using the ``when`` key makes it easier to restrict a step configuration
    to run only if any of the specified rules matches.
    The syntax is the same as in ``adjust`` and :tmt:story:`/spec/context`.

    Values can be single string with the rule or list of rules.

    .. code-block:: yaml

        report:
          - name: Open html report
            when:
            - trigger is not defined
            - initiator == human
            how: html
            open: true
          - how: display
