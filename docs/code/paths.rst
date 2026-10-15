.. _paths:

======================
    Anchor Paths
======================

Users can provide paths in the ``fmf`` metadata, for example
``ansible`` playbooks or local rpm packages to be installed by the
artifact prepare plugin. When such a path is relative, ``tmt``
needs a well-defined directory to resolve it against. That
directory is called an :term:`anchor path`.

There are two anchor paths with distinct purpose. Picking the
right one matters: the same relative string resolves to different
places depending on the anchor, and the wrong choice breaks cases
such as imported plans. The rule of thumb is simple:

* Does the path belong to the **run as a whole**, as something the
  user points at from the command line context? Use the
  :term:`base anchor path`.
* Does the path belong to a **specific node** (a plan, test or
  story) and travel together with its metadata? Use the
  :term:`node anchor path`.


.. _base-anchor-path:

Base Anchor Path
------------------------------------------------------------------

The :term:`base anchor path` is the run-wide default. It points to
the :term:`user tree` root, i.e. the ``fmf`` tree from which the
``tmt`` command was executed (or, when no tree is used, the
current working directory). For example:

.. code-block::

    /home/user/git/project

It is available in the code as ``plan.user_anchor_path`` and
should be used for paths that are meaningful relative to where the
user invoked ``tmt``, not relative to where a particular piece of
metadata happens to live. Current users are:

* artifact files fetched by the prepare step (e.g. ``rpm``
  packages or repository files stored locally)
* the relative ``path`` of the :ref:`/plugins/discover/fmf` plugin
  when no ``url`` is provided

Because it is derived from the run rather than from any single
node, the base anchor path is the same for every node in the run.


.. _node-anchor-path:

Node Anchor Path
------------------------------------------------------------------

The :term:`node anchor path` is node-specific. It points to the
``fmf`` tree root of the node the metadata belongs to (or the
current working directory when the node has no tree). It is
available in the code as ``node.anchor_path`` and should be used
for paths that are authored as part of a given node and are
expected to be relative to that node's ``fmf`` root. Current users
are:

* ``ansible`` playbooks in the prepare and finish steps
* the ``ansible`` inventory layout
* plan environment files
* ``fmf_id``, the fmf identifier of the respective node

The crucial property is that the node anchor path follows the
node, even when the node no longer lives in the :term:`user tree`:

* **Imported plans.** A remote plan is cloned into the
  :term:`import tree` and its metadata is loaded from there. The
  node's ``fmf`` root, and therefore its node anchor path, points
  into the import tree, so playbook paths keep resolving relative
  to the imported plan and not to the user tree.

* **Plan shaping.** When plans are derived from an existing one,
  for example by splitting a plan with the
  ``--max-tests-per-plan`` option, the derived plans inherit the
  original ``fmf`` root. Their node anchor path stays correct
  without any extra handling.


Relationship
------------------------------------------------------------------

For a plain local plan the two anchor paths point to the same
directory, because the node lives directly in the :term:`user
tree`. They diverge only when the node's tree is not the user
tree, such as for imported plans. Think of the node anchor path as
the base anchor path narrowed down to a specific node:

.. code-block::

    base anchor path   ->  user tree root           (per run)
    node anchor path   ->  node's own fmf root      (per node)

When in doubt, ask whether the path should still resolve correctly
if the plan were imported from another repository. If yes, it
belongs to the node and the :term:`node anchor path` is the right
choice.
