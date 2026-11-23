The :tmt:story:`/spec/plans/discover` step plugins gather tests
and their metadata for execution.

Use the :ref:`/plugins/discover/fmf` plugin to select tests from fmf
metadata, or the :ref:`/plugins/discover/shell` plugin to define tests
directly in a plan.

The default method is :ref:`shell </plugins/discover/shell>`.

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
