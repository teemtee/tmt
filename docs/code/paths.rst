.. _paths:

======================
    Path Handling
======================

Paths show up in several places of the fmf metadata and in the
code. Here we give them clear names and describe how they are
resolved so that we can clearly distinguish them.


.. _anchor-path:

anchor path
------------------------------------------------------------------

When a relative path is provided by the user, for example an
:ref:`/plugins/prepare/ansible` playbook for preparing the guest
or a local :ref:`/plugins/prepare/artifact` to be installed on the
guest, tmt resolves it against a well-defined directory called an
:term:`anchor path`. It is the fmf tree root of the node (a plan,
test or story) the metadata belongs to.

For the special case when there is no fmf tree root, for example
when running commands like ``tmt try fedora`` from your home
directory, the current working directory is used as the anchor.

For a plan defined directly in the :term:`user tree` the anchor
path is the user tree root:

.. code-block::

    /home/user/git/project

For an imported plan the anchor path points to the fmf tree root
under the :term:`import tree`, so that relative paths resolve
correctly the same way as when the plan runs in its own
repository:

.. code-block::

    # basic case when git root and fmf root are the same
    /var/tmp/tmt/run-123/import/plan

    # fmf root stored deeper in the git repository
    /var/tmp/tmt/run-123/import/plan/nested/tree


.. _fmf-path:

fmf path
------------------------------------------------------------------

The :term:`fmf path` is the ``path`` key of the :term:`fmf id`.
It points to the location of the fmf tree inside its git
repository, expressed as the relative path from the git repository
root to the fmf tree root and starting with a slash. It is used
for example by ``plan.import`` to find a plan stored deeper in the
repository.

For a tree stored directly in the git repository root the fmf path
is not needed. When the tree lives deeper, fmf path captures that
location. For testing we quite often use the ``data`` directories
with nested fmf trees used for testing specific features:

.. code-block::

    tmt
    ├── .fmf    <--- main fmf tree
    ├── .git    <--- git repo root
    └── tests
        └── feature
            ├── data
            │   ├── .fmf    <--- nested fmf tree
            │   ├── plan.fmf
            │   └── test.fmf
            ├── main.fmf
            └── test.sh

    git root: /home/user/git/tmt
    fmf root: /home/user/git/tmt/tests/feature/data
    fmf path: /tests/feature/data


.. _test-path:

test path
------------------------------------------------------------------

The :term:`test path` is the :tmt:story:`/spec/tests/path` key of
a test. It defines the directory to enter before the test is
executed, expressed as the path from the metadata tree root and
starting with a slash.

When not defined, the directory where the test metadata is stored
is used. So for the frequent use case when both test metadata
and test script are stored in the same directory, for example:

.. code-block::

    tmt
    ├── .fmf    <--- fmf tree root
    └── tests
        └── feature
            ├── main.fmf
            └── test.sh

... the default path is evaluated to ``/tests/feature`` and
does not need to be explicitly specified in test metadata:

.. code-block:: yaml

    summary: Test the feature
    test: ./test.sh

On the other hand, when several tests share the same test
script stored in a different directory, for example like this:

.. code-block::

    tmt
    ├── .fmf    <--- fmf tree root
    └── tests
        ├── area
        │   └── feature
        │       ├── one
        │       │   └── main.fmf
        │       └── two
        │           └── main.fmf
        └── common
            └── check.sh    <--- shared test script

... you might rather want to provide path to the directory with
the shared scripts instead of using possibly long relative paths
like ``../../../common/check.sh`` when the test metadata are buried
deeper in the directory structure:

.. code-block:: yaml

    summary: Lint the feature
    path: /tests/common
    test: ./check.sh --feature
