The :tmt:story:`/spec/plans/discover` step plugins gather tests
and their metadata for execution. Select a discovery method using
the ``how`` key.

.. _/plugins/discover/dist-git-source:

dist-git-source
---------------

.. Preserve the original story targets for existing cross-references.

.. tmt:story:: /spec/plans/discover/dist-git-source
    :title: dist-git-source

    Download rpm sources for dist-git repositories

    Downloads the source files specified in the ``sources``
    file of a DistGit (Fedora, CentOS) repository.  Plan using
    the option has to be defined in a DistGit repository or
    the ``url`` option needs to point to the root of such
    repository.

    All source files are available for further use in the
    directory provided in the ``TMT_SOURCE_DIR`` variable.

    Patches are applied by the ``rpmbuild -bp`` command which
    runs in ``prepare`` step on the provisioned guest, with
    order ``60``. All created files and directories by this command
    are directly in ``TMT_SOURCE_DIR``.

    To run the plan without uploading source files to the lookaside
    the type ``local`` can be used. Sources have to be listed in the ``sources``
    file and present in the same directory as the ``spec`` file.

    The :ref:`/plugins/discover/fmf` plugin supports
    additional dist-git options, see its documentation for
    details.

    .. note::

        In order to discover which tests would be executed,
        without actually running them, it is necessary to
        enable the `provision` and `prepare` steps as well:

        .. code-block::

            tmt run -v discover provision prepare finish

    .. code-block:: yaml

        # Download & extract sources from another repo, print
        # single file as a test
        discover:
            how: shell
            url: https://src.fedoraproject.org/rpms/tmt
            dist-git-source: true
            tests:
              - name: /print/pyproject
                test: cat $TMT_SOURCE_DIR/tmt-*/pyproject.toml

    .. code-block:: yaml

        # Just download sources, test is responsible for rpmbuild
        # and running tests
        discover:
            how: shell
            dist-git-source: true
            dist-git-download-only: true
            tests:
              - name: /unit
                test: >
                    rpmbuild -bp
                        --define "_sourcedir $TMT_SOURCE_DIR"
                        --define "_builddir $TMT_SOURCE_DIR/BUILD"
                        $TMT_SOURCE_DIR/*.spec &&
                    cd $TMT_SOURCE_DIR/BUILD/* &&
                    make test
                require:
                  - rpm-build

    .. code-block:: yaml

        # Source file wasn't uploaded to look aside yet, but exists next
        # to the spec file.
        discover:
          how: shell
          dist-git-source: true
          dist-git-type: local

.. _/plugins/discover/where:

where
-----

.. tmt:story:: /spec/plans/discover/where
    :title: where

    Execute tests on selected guests

    In the :tmt:story:`/spec/plans/provision/multihost` scenarios it
    is often necessary to execute test code on selected guests
    only or execute different test code on individual guests.
    The ``where`` key allows to select guests where the tests
    should be executed by providing their ``name`` or the
    ``role`` they play in the scenario. Use a list to specify
    multiple names or roles. By default, when the ``where``
    key is not defined, tests are executed on all provisioned
    guests.

    .. code-block:: yaml

        # Run a different script for each guest or role
        discover:
          - how: shell
            where: client
            tests:
              - name: run-the-client-code
                test: client.py
          - how: shell
            where: server
            tests:
              - name: run-the-server-code
                test: server.py

    .. code-block:: yaml

        # Filter different sets of tests for each guest or role
        discover:
          - how: fmf
            filter: tag:client-tests
            where: client
          - how: fmf
            filter: tag:server-tests
            where: server

.. _/plugins/discover/when:

when
----

.. tmt:story:: /spec/plans/discover/when
    :title: when

    Conditional step configuration

    Using the ``when`` key makes it easier to restrict a step configuration
    to run only if any of the specified rules matches.
    The syntax is the same as in ``adjust`` and :tmt:story:`/spec/context`.

    Values can be single string with the rule or list of rules.

    .. code-block:: yaml

        discover:
          - name: Private tests, applicable only for RHEL
            when: distro == rhel
            how: fmf
            url: https://secret
          - name: Public tests
            how: fmf
            url: https://public
          - name: Just a demo of more rules in the 'when' key
            how: shell
            tests:
              - name: something
                test: ./something.sh
            when:
            - initiator == konflux and distro == fedora
            - initiator == human and distro == fedora
