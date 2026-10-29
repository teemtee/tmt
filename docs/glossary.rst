========
Glossary
========

Here you can find some common terms used throughout the tmt project.

Machines
--------

.. glossary::

   guest
      The machine where the tests are being run.

   runner
      The machine that is running the ``tmt`` command.

Identifiers
-----------

.. glossary::

    fmf id
        An identifier used to uniquely define test, plan or story.
        Consists of ``name``, ``url``, ``ref`` and ``path``. See the
        `fmf identifier`_ documentation for detailed description of
        individual keys.

Directories
-----------

.. glossary::

    plan workdir
        Directory used for storing temporary files related to particular
        plan, e.g. ``/var/tmp/tmt/run-123/plans/core``.

    run workdir
        Working directory created for each run used for storing various
        temporary files needed during the test discovery and execution,
        e.g. ``/var/tmp/tmt/run-123/``.

    test tree
        Directory ``tests`` containing test code prepared by the
        ``discover`` step, e.g.
        ``/var/tmp/tmt/run-123/plans/core/discover/default-0/tests``.
        See :ref:`test-tree` for details.

    user tree
        The ``fmf`` tree from which the ``tmt`` command was executed,
        e.g. ``/home/user/git/project``. See :ref:`user-tree` for
        details.

    work tree
        Copy of the *user tree* stored under ``plan-workdir/tree``. Path
        to this directory is available in the ``TMT_TREE`` environment
        variable, e.g. ``/var/tmp/tmt/run-123/plans/core/tree``. See
        :ref:`work-tree` for details.

    import tree
        The ``fmf`` tree cloned into the *run workdir* under the
        ``import`` folder when a remote plan is imported, e.g.
        ``/var/tmp/tmt/run-123/import/plan``. See :ref:`import-tree` for
        details.

Paths
-----

.. glossary::

    anchor path
        The directory against which relative paths are resolved, the fmf
        metadata root by default, current working directory when no
        metadata are detected. See :ref:`anchor-path` for details.

    fmf path
        The ``path`` key of the :term:`fmf id`, pointing to the location
        of the fmf tree inside its git repository, for example
        ``/tests/feature/data``. See :ref:`fmf-path` for details.

    test path
        The :tmt:story:`/spec/tests/path` key of a test, defining the
        directory to enter before the test is executed, for example
        ``/common/scripts``. See :ref:`test-path` for details.


.. _fmf identifier: https://fmf.readthedocs.io/en/stable/concept.html#identifiers
