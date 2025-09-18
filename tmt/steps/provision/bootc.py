import os
from typing import TYPE_CHECKING, Optional, cast

import click

import tmt
import tmt.base
import tmt.hardware
import tmt.log
import tmt.steps
import tmt.steps.provision
import tmt.steps.provision.testcloud
import tmt.utils
from tmt.container import container, field
from tmt.steps.provision.testcloud import GuestTestcloud
from tmt.utils import Path
from tmt.utils.imagebuilder import PODMAN_ENV, PODMAN_MACHINE_NAME, BootcImageBuilder
from tmt.utils.templates import render_template

if TYPE_CHECKING:
    from tmt.hardware import Size

DEFAULT_TMP_PATH = "/var/tmp/tmt"  # noqa: S108

DEFAULT_IMAGE_BUILDER = "quay.io/centos-bootc/bootc-image-builder:latest"
CONTAINER_STORAGE_DIR = tmt.utils.Path("/var/lib/containers/storage")

DEFAULT_PODMAN_MACHINE_CPU = 2
DEFAULT_PODMAN_MACHINE_MEM: 'Size' = tmt.hardware.UNITS('2048 MB')
DEFAULT_PODMAN_MACHINE_DISK_SIZE: 'Size' = tmt.hardware.UNITS('50 GB')

CONTAINER_TEMPLATE = """
FROM {{ base_image }}

RUN <<EOF
set -euo pipefail

# install dependencies required by tmt
dnf -y install cloud-init rsync
ln -s ../cloud-init.target /usr/lib/systemd/system/default.target.wants
dnf clean all

# add the scripts in /var/lib/tmt/scripts to the PATH
touch /etc/environment
echo "export PATH=$PATH:/var/lib/tmt/scripts" >> /etc/environment

EOF
"""


class GuestBootc(GuestTestcloud):
    containerimage: Optional[str]
    _rootless: bool

    def __init__(
        self,
        *,
        data: tmt.steps.provision.GuestData,
        name: Optional[str] = None,
        parent: Optional[tmt.utils.Common] = None,
        logger: tmt.log.Logger,
        containerimage: Optional[str],
        rootless: bool,
    ) -> None:
        super().__init__(data=data, logger=logger, parent=parent, name=name)
        self.containerimage = containerimage
        self._rootless = rootless

    def remove(self) -> None:
        if not self._instance:
            return

        if self.containerimage:
            tmt.utils.Command("podman", "rmi", self.containerimage).run(
                cwd=self.workdir,
                stream_output=True,
                logger=self._logger,
                env=PODMAN_ENV if self._rootless else None,
            )

        try:
            tmt.utils.Command("podman", "machine", "rm", "-f", PODMAN_MACHINE_NAME).run(
                cwd=self.workdir, stream_output=True, logger=self._logger
            )
        except BaseException:
            self._logger.debug(
                "Unable to remove podman machine '{PODMAN_MACHINE_NAME}', it might not exist."
            )

        super().remove()


@container
class BootcData(tmt.steps.provision.testcloud.ProvisionTestcloudData):
    container_file: Optional[str] = field(
        default=None,
        option='--container-file',
        metavar='CONTAINER_FILE',
        help="""
             Path to a Containerfile for building the container image from scratch.
             This creates the initial container image that will be used by bootc image
             builder to create a disk image.

             Cannot be used with container-image.
             """,
    )

    derived_container_file: Optional[str] = field(
        default=None,
        option='--derived-container-file',
        metavar='CONTAINER_FILE',
        help="""
             Path to a Containerfile for building a derived image on top of an existing base image.
             This file will only be used when add-tmt-dependencies is enabled. It allows
             customization of the TMT dependency layer that gets added to the base container image.
             """,
    )

    container_file_workdir: str = field(
        default=".",
        option=('--container-file-workdir'),
        metavar='CONTAINER_FILE_WORKDIR',
        help="""
             Select working directory for the podman build invocation.
             """,
    )

    container_image: Optional[str] = field(
        default=None,
        option=('--container-image'),
        metavar='CONTAINER_IMAGE',
        help="""
             Select container image to be used to build a bootc disk.
             This takes priority over Containerfile.
             """,
    )

    add_tmt_dependencies: bool = field(
        default=True,
        is_flag=True,
        option=('--add-tmt-dependencies/--no-add-tmt-dependencies'),
        help="""
             Add tmt dependencies to the supplied container image or image built
             from the supplied Containerfile.
             This will cause a derived image to be built from the supplied image.
             """,
    )

    image_builder: str = field(
        default=DEFAULT_IMAGE_BUILDER,
        option=('--image-builder'),
        metavar='IMAGE_BUILDER',
        help="""
             The full repo:tag url of the bootc image builder image to use for
             building the bootc disk image.
             """,
    )

    rootfs: str = field(
        default="xfs",
        option=('--rootfs'),
        choices=['ext4', 'xfs', 'btrfs'],
        help="""
             Select root filesystem type. Overrides the default from the source
             container.
             """,
    )

    build_disk_image_only: bool = field(
        default=False,
        is_flag=True,
        option='--build-disk-image-only',
        help="""
             Only build a bootc disk image from a container image and quit.
             Guest VM will not start.
             """,
    )


@tmt.steps.provides_method('bootc')
class ProvisionBootc(tmt.steps.provision.ProvisionPlugin[BootcData]):
    """
    Provision a local virtual machine using a bootc container image

    Minimal config which uses the CentOS Stream 9 bootc image:

    .. code-block:: yaml

        provision:
            how: bootc
            container-image: quay.io/centos-bootc/centos-bootc:stream9
            rootfs: xfs

    Here's a config example using a Containerfile:

    .. code-block:: yaml

        provision:
            how: bootc
            container-file: "./my-custom-image.containerfile"
            container-file-workdir: .
            image-builder: quay.io/centos-bootc/bootc-image-builder:stream9
            rootfs: ext4
            disk: 100

    Another config example using an image that already includes tmt
    dependencies:

    .. code-block:: yaml

        provision:
            how: bootc
            add-tmt-dependencies: false
            container-image: localhost/my-image-with-deps
            rootfs: btrfs

    This plugin is an extension of the virtual.testcloud plugin.
    Essentially, it takes a container image as input, builds a
    bootc disk image from the container image, then uses the virtual.testcloud
    plugin to create a virtual machine using the bootc disk image.

    The bootc disk creation requires running podman as root. The plugin will
    automatically check if the current podman connection is rootless. If it is,
    a podman machine will be spun up and used to build the bootc disk.

    To trigger hard reboot of a guest, plugin uses testcloud API. It is
    also used to trigger soft reboot unless a custom reboot command was
    specified via ``tmt-reboot -c ...``.
    """

    _data_class = BootcData
    _guest_class = GuestTestcloud
    _guest = None
    _rootless = True

    @property
    def is_in_standalone_mode(self) -> bool:
        """
        Enable standalone mode when build_disk_image_only is True
        """

        if self.data.build_disk_image_only:
            return True
        return super().is_in_standalone_mode

    def _get_id(self) -> str:
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        parent = cast(tmt.steps.provision.Provision, self.parent)
        assert parent.plan is not None
        assert parent.plan.my_run is not None
        assert parent.plan.my_run.unique_id is not None
        return parent.plan.my_run.unique_id

    def _expand_path(self, relative_path: str) -> str:
        """
        Expand the path to the full path relative to the current working dir
        """

        if relative_path.startswith("/"):
            return relative_path
        return f"{os.getcwd()}/{relative_path}"

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Provision the bootc instance
        """

        super().go(logger=logger)

        data = BootcData.from_plugin(self)
        data.show(verbose=self.verbosity_level, logger=self._logger)

        # Image of file have to provided
        if data.container_image is None and data.container_file is None:
            raise tmt.utils.ProvisionError(
                "Either 'container-file' or 'container-image' must be specified."
            )

        containerimage: Optional[str] = None

        if not self.is_dry_run:
            assert self.workdir
            builder = BootcImageBuilder(self.data, self.workdir, self._logger)
            builder.handle_image(self._get_id())
        # Set unique disk file name, each plan will have its own disk file
        disk_file_name = Path(
            render_template(
                'disk-{{ PHASE.parent.plan.my_run.unique_id }}'
                '-{{ PHASE.parent.plan.pathless_safe_name }}'
                '-{{ PHASE.safe_name }}.qcow2',
                PHASE=self,
            )
        )

        assert self.workdir is not None

        image_dir = self.workdir / 'qcow2'

        # Rename disk file name to unique file name
        built_image = image_dir / 'disk.qcow2'
        renamed_image = image_dir / disk_file_name

        if not self.is_dry_run:
            built_image.rename(renamed_image)
        data.image = f"file://{renamed_image}"

        if data.build_disk_image_only:
            self.info("The disk image is converted and saved")
            click.echo(tmt.log.indent(data.image, level=2))
            return

        self._guest = GuestBootc(
            logger=self._logger,
            data=data,
            name=self.name,
            parent=self.step,
            containerimage=containerimage,
            rootless=self._rootless,
        )
        self._guest.start()
        self._guest.setup()
