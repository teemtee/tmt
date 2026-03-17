.. _trees:

======================
    Tree Handling
======================

The ``fmf`` trees holding test, plan and story metadata are used
at several places of the code and their data is copied to multiple
locations. Here we give them clear names so that we can clearly
distinguish them.


.. _user-tree:

User Tree
------------------------------------------------------------------

The initial ``fmf`` tree from which ``tmt`` commands are executed
is called **user tree**. For example:

.. code-block::

    /home/user/git/tests/nested

By default it is detected from the current working directory. It
can be directly ``$PWD`` or the closest parent which contains
``.fmf`` directory marking root of the ``fmf`` tree as implemented
by ``fmf``. Alternatively it can be provided using the ``--root``
option.

All the following cases result in the ``fmf`` root mentioned
above:

.. code-block::

    tmt --root /home/user/git/tests/nested
    tmt --root /home/user/git/tests/nested/deeper
    cd /home/user/git/tests/nested && tmt
    cd /home/user/git/tests/nested/deeper && tmt


.. _work-tree:

Work Tree
------------------------------------------------------------------

When a new run is created, the *user tree* is copied into the run
workdir under the ``tree`` folder and its path is made available
in the ``TMT_TREE`` environment variable. For example this is a
**runner work tree**:

.. code-block::

    runner:/var/tmp/tmt/run-123/plan/tree

Runner work tree is synced to the **guest work tree** so that
tests defined by the :ref:`/plugins/discover/shell` discover
plugin or prepare :ref:`/plugins/prepare/shell` phases can use
files and scripts from there.

.. code-block::

    guest:/var/tmp/tmt/run-123/plan/tree


.. _test-tree:

Test Tree
------------------------------------------------------------------

The discover plugin prepares a ``tests`` directory where test
scripts and files are available for test execution. This directory
is called a **test tree**.

The :ref:`/plugins/discover/fmf` discover plugin copies *user
tree* to *test tree* when ``url`` is not provided. Otherwise the
whole git repository is cloned into it.

The :ref:`/plugins/discover/shell` discover plugin creates a
symlink to the *work tree* so the resulting structure looks like
this:

.. code-block::

    ├── discover
    │   ├── default-0
    │   │   └── tests -> ../../tree
    │   ├── step.yaml
    │   └── tests.yaml
