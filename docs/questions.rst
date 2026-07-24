.. _questions:

======================
    Questions
======================

.. _fmf-and-tmt:


What is the difference between fmf and tmt?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `Flexible Metadata Format`__ or ``fmf`` is a plain text format
based on ``yaml`` used to store data in both human and machine
readable way close to the source code. Thanks to inheritance and
elasticity, metadata are organized in the structure efficiently,
preventing unnecessary duplication.

__ https://fmf.readthedocs.io/en/latest/

The `Test Management Tool`__ or ``tmt`` is a project which
consists of the :ref:`specification` which defines how tests,
plans and stories are organized, python modules implementing the
specification and the command-line tool which provides a
user-friendly way to create, debug and easily run tests.

__ https://tmt.readthedocs.io/en/latest/


.. _libvirt:


Who is using tmt?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Are there any example projects which are using ``tmt`` which I
could use as an inspiration for my initial configuration setup?

* The `HealthTrio Success Story`__ with CentOS Stream and tmt
* The `AlmaLinux`__ community is using tmt for its compose testing

__ https://blog.centos.org/2024/01/managing-internal-ci-tests-with-tmt-for-centos-stream-updates/
__ https://github.com/AlmaLinux/compose-tests


Using tmt outside of Fedora, CentOS and RHEL distribution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The tmt is packaged and tested only for these three flavors,
however if one :ref:`installs<pip_install>` tmt from the PyPI it
can be run also on other Linux distributions.

The caveat is that installation of required packages depends on
the usage of ``rpm``, ``yum`` or ``dnf``. When tmt is executed on
the host none of these commands is necessary so tmt should work
once ``pip install`` succeeds.

On the other hand - when tmt is used to execute tests on
provisioned guest it depends if the plan will try to install any
packages (either by test :tmt:story:`/spec/tests/require`,
:tmt:story:`/spec/tests/recommend` or using prepare
:ref:`/plugins/prepare/install` plugin) it will fail as tmt
currently doesn't work with other package management tools. This
can be worked around by installing the test dependencies (as well
as the ``rsync`` command) using :ref:`/plugins/prepare/ansible`
or :ref:`/plugins/prepare/shell` prepare plugins.


Virtualization Tips
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In order to safely run tests under a virtual machine started on
your laptop you only need to install the ``tmt+provision-virtual``
package. By default the ``session`` connection is used so no other
steps should be needed, just execute tests using the ``tmt run``
command.

If you want to use the ``system`` connection you might need to do
a few steps to set up your box. Here's just a couple of hints how
to get the virtualization quickly working on your laptop. See the
`Getting started with virtualization`__ docs to learn more.

Make sure the ``libvirtd`` is running on your box:

.. code-block:: shell

    sudo systemctl start libvirtd

Add your user account to the libvirt group:

.. code-block:: shell

    sudo usermod -a -G libvirt $USER

Note that you might need to restart your desktop session to get it
fully working. Or at least start a new login shell:

.. code-block:: shell

    su - $USER

In some cases you might also need to activate the default network
device:

.. code-block:: shell

    sudo virsh net-start default

Here you can find vm `images for download`__.

__ https://docs.fedoraproject.org/en-US/quick-docs/getting-started-with-virtualization/
__ https://kojipkgs.fedoraproject.org/compose/


Container Package Cache
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using containers can speed up your testing. However, fetching
package cache can slow things down substantially. Use this set of
commands to prepare a container image with a fresh dnf cache:

.. code-block:: shell

    podman run -itd --name fresh fedora
    podman exec fresh dnf makecache
    podman image rm fedora:fresh
    podman commit fresh fedora:fresh
    podman container rm -f fresh

Then specify the newly created image in the provision step:

.. code-block:: shell

    tmt run --all provision --how container --image fedora:fresh

In this way you can save up to several minutes for each plan.


Nitrate Migration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After a nitrate test case is migrated to ``fmf`` git becomes the
canonical source of the test case metadata. All further changes
should be done in git and updates synchronized back to nitrate
using ``tmt test export . --how nitrate`` command. Otherwise direct
changes in Nitrate might be lost.

A unique identifier of the new test metadata location is stored in
the ``[fmf]`` section of test case notes. Below is the list of
attributes which are synchronized to corresponding nitrate fields:

* component — components tab
* contact — default tester
* description — purpose-file in the structured field
* duration — estimated time
* enabled — status
* environment — arguments
* summary — description in the structured field
* tag — tags tab
* tier — tags (e.g. ``1`` synced to the ``Tier1`` tag)

The following attributes, if present, are exported as well:

* extra-hardware — hardware in the structured field
* extra-pepa — pepa in the structured field
* extra-summary — Nitrate test case summary
* extra-task — Nitrate test case script

They have the ``extra`` prefix as they are not part of the L1
Metadata Specification and are supposed to be synced temporarily
to keep backward compatibility.


.. _restraint-compatibility:

Restraint Compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For backward-compatibility ``tmt`` provides selected commands
of the `restraint`__ framework so that existing tests can be more
easily migrated. Currently the following scripts are supported:

* ``rhts-abort`` and ``rstrnt-abort`` — :tmt:story:`/stories/features/abort`
* ``rhts-reboot`` and ``rstrnt-reboot`` — :tmt:story:`/stories/features/reboot`
* ``rhts-submit-log`` and ``rstrnt-report-log`` — :tmt:story:`/stories/features/report-log`
* ``rhts-report-result`` and ``rstrnt-report-result`` — :tmt:story:`/stories/features/report-result`

Note that these scripts cover only the common use cases and some
of their irrelevant options, such as ``--server`` used for the
restraint server, are ignored.

.. warning::

    If your tests depend on these compatibility scripts, please
    ensure that the ``restraint-compatible`` option is enabled
    under the :ref:`/plugins/execute/tmt` execute step.

    .. code-block:: yaml

        execute:
            how: tmt
            restraint-compatible: true

    If possible, we recommend to update your existing tests and
    use ``tmt-abort``, ``tmt-reboot``, ``tmt-file-submit`` and
    ``tmt-report-result`` scripts instead. These are not planned
    to be removed and will be supported in the future.

.. note::

    Currently this functionality is enabled by default but will be
    removed according to the following schedule:

    * March 2026 ... print warning for all restraint features used
      without the ``restraint-compatible`` flag enabled
    * September 2026 ... send email reminders about the planned
      deprecation to all users identified to be still using them
    * January 2027 ... no backward compatibility features are
      enabled without the ``restraint-compatible`` flag enabled

    See the `tracking issue`__ for more details about the
    deprecation and progress of the effort.

.. versionadded:: 1.59

   When ``restraint-compatible`` is set, an environment variable
   ``RSTRNT_TASKNAME`` is set with a value equivalent to that of
   ``TMT_TEST_NAME``.

__ https://restraint.readthedocs.io/
__ https://github.com/teemtee/tmt/issues/4021


.. _mulithost-compatibility:

Multihost Compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Some older tests might be using the ``CLIENTS`` and ``SERVERS``
environment variables to get the information about the guests
involved in the multihost testing. In order to provide these
variables to all tests in a tmt plan it is possible to use the
``TMT_PLAN_ENVIRONMENT_FILE`` variable and set them based on the
:tmt:story:`/spec/plans/guest-topology`. The example below demonstrates
the usage on a simple tmt plan:

.. code-block:: yaml

    provision:
      - name: server
        how: virtual
        connection: system
      - name: client
        how: virtual
        connection: system

    prepare:
      - summary: Export client and server hostname for all tests
        how: shell
        script: |
            source "$TMT_TOPOLOGY_BASH"
            echo "CLIENTS=${TMT_GUESTS[client.hostname]}" >> "$TMT_PLAN_ENVIRONMENT_FILE"
            echo "SERVERS=${TMT_GUESTS[server.hostname]}" >> "$TMT_PLAN_ENVIRONMENT_FILE"

    execute:
        how: tmt
        script: |
            echo "clients: $CLIENTS"
            echo "servers: $SERVERS"


Why is the 'id' key added to my test during export?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When exporting ``tmt`` test metadata using ``tmt tests export`` to
other test case management systems, a unique ``id`` is created in
order to provide a persistent way to identify the test even if it
is renamed, moved across the directory structure or into a
different repository. See the :tmt:story:`/spec/core/id` key
specification for more details.


How can I integrate tmt tests with other tools?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each tmt test has a unique `fmf identifier`__ which can look like
this:

.. code-block:: yaml

    name: /tests/core/docs
    url: https://github.com/teemtee/tmt.git
    ref: main

These identifiers can be used for integration with other tools,
for example to execute tmt tests using custom workflows. For this
use case ``tmt tests export`` command can be used to produce a
list of fmf identifiers of selected tests:

.. code-block:: shell

    tmt tests export --fmf-id | custom-workflow --fmf-id -
    tmt tests export core/docs --fmf-id | custom-workflow --fmf-id -

Custom workflow can then consume generated ids and perform desired
actions such as fetch the tests and execute them.

__ https://fmf.readthedocs.io/en/latest/concept.html#identifiers
