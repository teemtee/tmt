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

    test tree
        Directory ``tests`` containing test code prepared by the
        ``discover`` step, e.g.
        ``/var/tmp/tmt/run-123/plan/discover/default-0/tests``.
        See :ref:`test-tree` for details.

    user tree
        The ``fmf`` tree from which the ``tmt`` command was executed,
        e.g. ``/home/user/git/project``. See :ref:`user-tree` for
        details.

    work tree
        Copy of the *user tree* stored under ``plan-workdir/tree``. Path
        to this directory is available in the ``TMT_TREE`` environment
        variable, e.g. ``/var/tmp/tmt/run-123/plan/tree``. See
        :ref:`work-tree` for details.

    run workdir
        Working directory created for each run used for storing various
        temporary files needed during the test discovery and execution,
        e.g. ``/var/tmp/tmt/run-123/``.

    plan workdir
        Directory used for storing temporary files related to particular
        plan, e.g. ``/var/tmp/tmt/run-123/plan/one``.
