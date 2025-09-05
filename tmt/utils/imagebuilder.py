import uuid
from typing import Any, Optional

import tmt
import tmt.log
import tmt.utils
from tmt.utils import Path

PODMAN_MACHINE_NAME = 'podman-machine-tmt'
PODMAN_ENV = tmt.utils.Environment.from_dict(
    {"CONTAINER_CONNECTION": f'{PODMAN_MACHINE_NAME}-root'}
)

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

    def _handle_image_tag(self) -> None:
        """Assign a unique 4-character UUID to the image tag if not set."""
        if not self.data.image_tag:
            self.data.image_tag = str(uuid.uuid4())[:4]
            self._logger.debug(f"Generated new image tag: {self.data.image_tag}")

    def _build_and_push_image(self, derived_image_name: str) -> str:
        """
        Build a custom derived image, push it to the registry, and return its URL.
        """
        built_image = self._build_derived_image(
            self.data.derived_container_file, derived_image_name, self.workdir
        )
        self._login_to_registry()
        self._push_container_image(built_image)

        image_url = f"{self.data.base_repo}/{built_image}"
        self._logger.info(f"Successfully built and pushed image: {image_url}")
        return image_url

    def _login_to_registry(self) -> None:
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

    def _push_container_image(self, container_image: str) -> None:
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

    def _build_base_image(self, container_file: str, image_name: str, build_dir: str) -> str:
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

    def _build_derived_image(
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

        try:
            tmt.utils.Command(
                "podman",
                "build",
                "--platform",
                arch_to_platform_dict[f'{self.data.arch}'],
                "-f",
                f"{container_file}",
                "-t",
                image_name,
                build_dir.resolve(),
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
