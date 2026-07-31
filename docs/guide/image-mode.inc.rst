.. _image-mode:

Testing in Image Mode
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`Image Mode`__ is an approach to deploying and managing RHEL and
Fedora-based operating systems using `bootc`__ container images.
In Image Mode, the OS is delivered as a container image managed
by ``bootc``, rather than being installed and updated using
traditional package managers.

__ https://www.redhat.com/en/technologies/linux-platforms/enterprise-linux/image-mode
__ https://containers.github.io/bootc/

When ``tmt`` detects that a provisioned guest is running in Image
Mode (by checking the output of ``bootc status``), it
automatically adjusts its behavior during the prepare step.
Instead of executing commands directly on the running system,
``tmt`` collects them into a ``Containerfile``, builds a new
container image, switches to it using ``bootc switch``, and
reboots the guest.


.. _image-mode-provisioning:

Provisioning an Image Mode Guest
------------------------------------------------------------------

There are several ways to provision an Image Mode guest for
testing:

Using the bootc plugin
^^^^^^^^^^^^^^^^^^^^^^

The :ref:`/plugins/provision/bootc` plugin builds a bootc disk
image from a container image and boots a local virtual machine
from it:

.. code-block:: yaml

    provision:
        how: bootc
        container-image: quay.io/centos-bootc/centos-bootc:stream9
        rootfs: xfs

This approach gives full control over the container image used
for testing. See the :ref:`/plugins/provision/bootc` plugin
documentation for all available options including
``container-file`` for custom Containerfiles.

Using pre-built qcow2 images
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Services like `Testing Farm`__ provide pre-built qcow2 images
that boot directly in Image Mode. In this case, use the
:ref:`/plugins/provision/virtual.testcloud` plugin with a
qcow2 image URL:

.. code-block:: yaml

    provision:
        how: virtual
        image: https://example.com/path/to/image-mode.x86_64.qcow2

__ https://docs.testing-farm.io/

No special configuration is needed — ``tmt`` detects Image Mode
automatically at runtime via ``bootc status``.

Using Beaker
^^^^^^^^^^^^

The :ref:`/plugins/provision/beaker` plugin supports provisioning
Image Mode guests on bare metal using the ``bootc`` option:

.. code-block:: yaml

    provision:
        how: beaker
        bootc: true
        bootc-image-url: quay.io/centos-bootc/centos-bootc:stream9

See the :ref:`/plugins/provision/beaker` plugin documentation for
additional options such as ``bootc-registry-secret``.


.. _image-mode-prepare:

How Prepare Steps Work in Image Mode
------------------------------------------------------------------

In Image Mode, the prepare step uses a **deferred execution
model**. Instead of running commands immediately on the guest,
certain prepare plugins collect their operations as ``RUN``
directives in a ``Containerfile``. At the end of the prepare
step, ``tmt``:

1. Writes the collected directives into a ``Containerfile``
2. Builds a new container image using ``podman build``
3. Switches to the new image using ``bootc switch``
4. Reboots the guest to activate the new image

The following prepare plugins use deferred execution in Image
Mode:

* :ref:`/plugins/prepare/install` — Package installation commands
  are collected as ``RUN`` directives. Both named packages and
  local RPMs are handled this way.

* :ref:`/plugins/prepare/shell` — Shell scripts are collected as
  ``RUN`` directives and execute during ``podman build``, **not**
  on the running guest. This is a critical difference from
  traditional provisioning — see :ref:`image-mode-caveats` below.

The following prepare plugins execute immediately on the live
guest, even in Image Mode:

* :ref:`/plugins/prepare/ansible` — Ansible playbooks are run
  directly on the guest, not deferred into the ``Containerfile``.

All deferred operations across all prepare phases are batched
into a **single** ``Containerfile`` build. Only one reboot
happens at the end of the entire prepare step, regardless of
how many prepare phases are defined.


.. _image-mode-caveats:

Caveats and Limitations
------------------------------------------------------------------

Shell scripts run during image build
    The :ref:`/plugins/prepare/shell` plugin collects scripts as
    ``RUN`` directives in the ``Containerfile``. This means
    they execute in a ``podman build`` context, **not** on the
    live system. As a consequence:

    * There are no running services (no ``systemd``, no
      ``dbus``, no network services).
    * Live system state such as ``/proc`` or ``/sys`` values is
      not available.
    * Any files created on the running guest before the prepare
      step are not visible inside the build.
    * Data written to ``/var`` during the container build is
      **not** applied to the live system after ``bootc switch``.
      This is due to the `three-way merge`__ mechanism used by
      ``bootc`` — the contents of ``/var`` from the image are
      only used during initial provisioning and are ignored on
      subsequent image switches. Use ``/usr`` or ``/usr/share``
      instead for data that must persist from the image.

    __ https://developers.redhat.com/articles/2025/08/25/what-image-mode-3-way-merge

    If your prepare scripts need to interact with running
    services or write to ``/var``, use the
    :ref:`/plugins/prepare/ansible` plugin instead, which
    executes directly on the guest.

Single reboot at step completion
    All deferred operations are applied in one build and reboot
    cycle at the end of the prepare step. There is no per-phase
    reboot between individual prepare phases.

FIPS feature is not supported
    The :ref:`prepare feature </plugins/prepare-feature>` for
    enabling FIPS is not supported on ostree-based or container
    systems and raises an error.

Helper scripts location
    On ostree-based systems (including Image Mode guests),
    ``tmt`` helper scripts (``tmt-reboot``, ``tmt-abort``,
    ``tmt-file-submit``, ``tmt-report-result``) are deployed to
    ``/var/lib/tmt/scripts`` instead of the default
    ``/usr/local/bin``. The directory is added to ``$PATH`` via
    ``/etc/profile.d/tmt.sh``, which means the scripts are only
    available in shells that load profile scripts (such as
    ``bash``). The ``TMT_SCRIPTS_DIR`` environment variable can
    be used to override this location.

Other steps work normally
    The ``discover``, ``execute``, ``report`` and ``finish``
    steps run normally on the rebooted guest after the new image
    has been applied. No special Image Mode handling is needed
    for these steps.
