import uuid
from typing import TYPE_CHECKING, Any, Optional

import tmt
import tmt.hardware
import tmt.log
import tmt.utils
from tmt.utils import Path
from tmt.utils.templates import render_template

if TYPE_CHECKING:
    from tmt.hardware import Size

DEFAULT_TMP_PATH = "/var/tmp/tmt"  # noqa: S108
PODMAN_MACHINE_NAME = 'podman-machine-tmt'
PODMAN_ENV = tmt.utils.Environment.from_dict(
    {"CONTAINER_CONNECTION": f'{PODMAN_MACHINE_NAME}-root'}
)
DEFAULT_IMAGE_BUILDER = "quay.io/centos-bootc/bootc-image-builder:latest"
CONTAINER_STORAGE_DIR = tmt.utils.Path("/var/lib/containers/storage")

DEFAULT_PODMAN_MACHINE_CPU = 2
DEFAULT_PODMAN_MACHINE_MEM: 'Size' = tmt.hardware.UNITS('2048 MB')
DEFAULT_PODMAN_MACHINE_DISK_SIZE: 'Size' = tmt.hardware.UNITS('50 GB')

# Translate arch to os/arch needed for podman build.
arch_to_platform_dict = {
    "x86_64": "linux/amd64",
    "aarch64": "linux/arm64",
    "ppc64le": "linux/ppc64le",
    "s390x": "linux/s390x",
}


class ImageBuilder:
    """
    Separate class to handle  image building logic,
    with improved error handling and logging for easier debugging.
    """

    def __init__(self, data: Any, workdir: Path, logger: tmt.log.Logger):
        self.data = data
        self.workdir = workdir
        self._logger = logger

    def build_and_push_image(self, derived_image_name: str) -> str:
        """
        Build a custom derived image, push it to the registry, and return its URL.
        """
        built_image = self.build_derived_image(
            self.data.derived_container_file, derived_image_name, self.workdir
        )
        self.login_to_registry()
        self.push_container_image(built_image)

        image_url = f"{self.data.base_repo}/{built_image}"
        self._logger.info(f"Successfully built and pushed image: {image_url}")
        return image_url

    def _handle_image_tag(self) -> None:
        """Assign a unique 4-character UUID to the image tag if not set."""
        if not self.data.image_tag:
            self.data.image_tag = str(uuid.uuid4())[:4]
            self._logger.debug(f"Generated new image tag: {self.data.image_tag}")

    def login_to_registry(self) -> None:
        """Log in to the container registry using the provided credentials."""
        self._logger.debug(f"Logging in to registry at {self.data.base_repo}.")
        try:
            tmt.utils.ShellScript(
                f"podman login -u {self.data.bootc_registry_user} -p "
                f"{self.data.bootc_registry_password} {self.data.base_repo}"
            ).to_shell_command().run(cwd=self.workdir, logger=self._logger)
            self._logger.info("Successfully logged in to registry.")
        except tmt.utils.RunError as exc:
            raise tmt.utils.ProvisionError(
                f"Failed to log in to the container registry.\n{exc.stdout}"
            ) from exc

    def push_container_image(self, container_image: str) -> None:
        """Push a container image to the configured registry."""
        remote_image_path = f"{self.data.base_repo}/{container_image}"
        self._logger.debug(f"Pushing image '{container_image}' to '{remote_image_path}'.")
        try:
            tmt.utils.Command(
                "podman",
                "push",
                "--tls-verify=false",
                "--quiet",
                container_image,
                remote_image_path,
            ).run(
                cwd=self.workdir,
                stream_output=True,
                logger=self._logger,
                env=None,
            )
            self._logger.info(f"Successfully pushed image: {remote_image_path}")
        except tmt.utils.RunError as exc:
            raise tmt.utils.ProvisionError(
                "Failed to push the container image to the registry.\n{exc.stdout}"
            ) from exc

    def _use_existing_image(self) -> str:
        """Returns the URL of a pre-existing bootc image."""
        if not self.data.image_url:
            raise tmt.utils.ProvisionError("image_url is required when not customizing image")
        self._logger.info(f"Using existing image: {self.data.image_url}")
        return str(self.data.image_url)

    def build_base_image(self, container_file: str, image_name: str, build_dir: str) -> str:
        """
        Build a container image from a Containerfile in a specific working directory.
        """
        self._logger.debug(f"Building base container image from {container_file}.")

        try:
            tmt.utils.Command(
                "podman",
                "build",
                Path(build_dir).resolve(),
                "-f",
                container_file,
                "-t",
                image_name,
            ).run(
                cwd=self.workdir,
                stream_output=True,
                logger=self._logger,
            )
            self._logger.info(f"Successfully built base image: {image_name}")
        except tmt.utils.RunError as e:
            raise tmt.utils.ProvisionError(
                "Failed to build the base container image.\n{exc.stdout}"
            ) from e

        return image_name

    def build_derived_image(
        self,
        container_file: str,
        image_name: str,
        build_dir: Path,
        rootless: Optional[bool] = False,
    ) -> str:
        """
        Build a derived container image from a base image and templates.
        """
        self._logger.debug("Building derived container image.")
        platform = arch_to_platform_dict.get(f'{self.data.arch}')
        if not platform:
            raise tmt.utils.ProvisionError("arch {self.data.arch} is not supported.")
        try:
            tmt.utils.Command(
                "podman",
                "build",
                "--platform",
                platform,
                "-f",
                container_file,
                "-t",
                image_name,
                Path(build_dir).resolve(),
            ).run(
                cwd=self.workdir,
                stream_output=True,
                logger=self._logger,
                env=PODMAN_ENV if rootless else None,
            )
            self._logger.info(f"Successfully built derived image: {image_name}")
        except tmt.utils.RunError as e:
            raise tmt.utils.ProvisionError(
                "Failed to build the derived container image.\n{exc.stdout}"
            ) from e

        return image_name

    def _create_template(self, template: str, base_image: str) -> str:
        assert self.workdir is not None  # narrow type

        containerfile_parsed = render_template(template, base_image=base_image)
        (self.workdir / 'Containerfile').write_text(containerfile_parsed)

        return str(self.workdir / 'Containerfile')

    def handle_image(self, *args: Any, **kwargs: Any) -> Any:
        """
        Flexible base method for image handling. Subclasses must implement this method
        with their specific signature and return type.
        """
        raise NotImplementedError


class BootcImageBuilder(ImageBuilder):
    """
    Separate class to handle  image building logic,
    with improved error handling and logging for easier debugging.
    """

    containerfile_template = '''
        FROM {{ base_image }}

        RUN \
        dnf -y install cloud-init rsync && \
        ln -s ../cloud-init.target /usr/lib/systemd/system/default.target.wants && \
        rm /usr/local -rf && ln -sr /var/usrlocal /usr/local && mkdir -p /var/usrlocal/bin && \
        dnf clean all
    '''

    def build_bootc_disk(self, containerimage: str, image_builder: str, rootfs: str) -> None:
        """
        Build the bootc disk from a container image using bootc image builder
        """

        self._logger.debug("Build bootc disk image.")

        tmt.utils.Command(
            "podman",
            "run",
            "--rm",
            "--privileged",
            "-v",
            f'{CONTAINER_STORAGE_DIR}:{CONTAINER_STORAGE_DIR}',
            "--security-opt",
            "label=type:unconfined_t",
            "-v",
            f"{self.workdir}:/output",
            image_builder,
            "build",
            "--type",
            "qcow2",
            "--rootfs",
            rootfs,
            "--local",
            containerimage,
        ).run(
            cwd=self.workdir,
            stream_output=True,
            logger=self._logger,
            env=PODMAN_ENV if self._rootless else None,
        )

    def _init_podman_machine(self) -> None:
        try:
            tmt.utils.Command("podman", "machine", "rm", "-f", PODMAN_MACHINE_NAME).run(
                cwd=self.workdir, stream_output=True, logger=self._logger
            )
        except BaseException:
            self._logger.debug("Unable to remove existing podman machine (it might not exist).")

        self._logger.debug("Initialize podman machine.")
        # fmt: off
        tmt.utils.Command(
            "podman", "machine", "init", "--rootful",
            "--disk-size", f"{DEFAULT_PODMAN_MACHINE_DISK_SIZE.magnitude}",
            "--memory", f"{DEFAULT_PODMAN_MACHINE_MEM.magnitude}",
            "--cpus", f"{DEFAULT_PODMAN_MACHINE_CPU}",
            "-v", f"{DEFAULT_TMP_PATH}:{DEFAULT_TMP_PATH}",
            "-v", "$HOME:$HOME",
            PODMAN_MACHINE_NAME,
        ).run(cwd=self.workdir, stream_output=True, logger=self._logger)
        # fmt: on

        self._logger.debug("Start podman machine.")
        tmt.utils.Command("podman", "machine", "start", PODMAN_MACHINE_NAME).run(
            cwd=self.workdir, stream_output=True, logger=self._logger
        )

    def _check_if_podman_is_rootless(self) -> None:
        output = tmt.utils.Command(
            "podman", "info", "--format", "{{.Host.Security.Rootless}}"
        ).run(cwd=self.workdir, stream_output=True, logger=self._logger)
        self._rootless = output.stdout == "true\n"

    def handle_image(self, unique_id: str) -> None:
        base_image_name = f'localhost/tmtbase-{unique_id}'
        derived_image_name = f'localhost/tmtmodified-{unique_id}'
        self._check_if_podman_is_rootless()

        if self._rootless:
            self._init_podman_machine()

        # Use provided container image
        if self.data.container_image is not None:
            containerimage = self.data.container_image
            if self.data.add_tmt_dependencies:
                container_file = self.data.derived_container_file or self._create_template(
                    self.containerfile_template, containerimage
                )
                containerimage = self.build_derived_image(
                    container_file, derived_image_name, self.workdir, self._rootless
                )
            self.build_bootc_disk(containerimage, self.data.image_builder, self.data.rootfs)

        # Build image according to the container file
        elif self.data.container_file is not None:
            containerimage = self.build_base_image(
                self.data.container_file, base_image_name, self.data.container_file_workdir
            )
            if self.data.add_tmt_dependencies:
                container_file = self.data.derived_container_file or self._create_template(
                    self.containerfile_template, containerimage
                )
                containerimage = self.build_derived_image(
                    container_file, derived_image_name, self.workdir, self._rootless
                )
            self.build_bootc_disk(containerimage, self.data.image_builder, self.data.rootfs)


class BootcBeakerImageBuilder(ImageBuilder):
    def handle_image(self, derived_image_name: str) -> None:
        # TODO: modify this function, if we decide to support build and push image
        # in mrack plugin, or remove it if not.
        pass
