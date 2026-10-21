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
        A directory against which relative paths provided by the user
        are resolved. There are two of them, the :term:`base anchor
        path` and the :term:`node anchor path`. See :ref:`paths` for
        details.

    base anchor path
        The run-wide default :term:`anchor path`. Defaults to the
        :term:`user tree` root (or the current working directory when no
        tree is used). Used for inputs that belong to the run as a whole
        rather than to a specific node, for example local rpm files to
        be installed by the artifact prepare plugin. See
        :ref:`base-anchor-path` for details.

    node anchor path
        The :term:`anchor path` of a **specific node**. It is the node's
        own ``fmf`` tree root (or the current working directory when the
        node has no tree), so it narrows the :term:`base anchor path`
        down to the plan, test or story the metadata belongs to. Used
        for paths owned by a particular node, such as ``ansible``
        playbooks or plan environment files. See :ref:`node-anchor-path`
        for details.
