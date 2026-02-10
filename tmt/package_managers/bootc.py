import re
import uuid
from typing import Any, Optional

import tmt.utils
from tmt.container import PYDANTIC_V1, ConfigDict, MetadataContainer
from tmt.package_managers import (
    Installable,
    Options,
    PackageManager,
    PackageManagerEngine,
    provides_package_manager,
)
from tmt.utils import (
    Command,
    CommandOutput,
    GeneralError,
    Path,
    RunError,
    ShellScript,
)

LOCALHOST_BOOTC_IMAGE_PREFIX = "localhost/tmt"


class BootcMetadataContainer(MetadataContainer):
    """
    Metadata container for bootc images.
    References the official bootc host v1 JSON schema(https://bootc-dev.github.io/bootc/host-v1.schema.json).
    This is a minimal version only including relevant fields for tmt.
    """

    if PYDANTIC_V1:

        class Config(MetadataContainer.Config):
            # Allow unknown fields to support schema extensions and newer bootc versions
            extra = "allow"
    else:
        model_config = ConfigDict(extra="allow")


class ImageReference(BootcMetadataContainer):
    image: str


class ImageStatus(BootcMetadataContainer):
    image: ImageReference


class BootEntry(BootcMetadataContainer):
    image: Optional[ImageStatus] = None


class HostStatus(BootcMetadataContainer):
    booted: Optional[BootEntry] = None


class BootcHost(BootcMetadataContainer):
    status: Optional[HostStatus] = None


class BootcEngine(PackageManagerEngine):
    containerfile_directives: list[str]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize bootc engine for package management"""
        super().__init__(*args, **kwargs)

        self.aux_engine = self.guest.bootc_builder._engine_class(*args, **kwargs)
        self.containerfile_directives = []

    def open_containerfile_directives(self) -> None:
        """Initialize containerfile directives"""

        if self.containerfile_directives:
            self.debug('Already collecting containerfile directives.')
            return

        self.debug('Starting collection of directives for new container file.')

        self.containerfile_directives = self._get_base_containerfile_directives()

    def flush_containerfile_directives(self) -> None:
        self.debug('Closing collection of directives for a container file.')

        self.containerfile_directives = []

    def prepare_command(self) -> tuple[Command, Command]:
        """
        Prepare installation command for bootc
        """
        assert self.guest.facts.sudo_prefix is not None  # Narrow type

        command = Command('bootc')

        if self.guest.facts.sudo_prefix:
            command = Command(self.guest.facts.sudo_prefix, 'bootc')

        return command, Command('')

    def _get_current_bootc_image(self) -> str:
        """Get the current bootc image running on the system"""

        command, _ = self.prepare_command()
        command += Command('status', '--json')

        if not (output := self.guest.execute(command, silent=True).stdout):
            raise tmt.utils.PrepareError("Failed to get current bootc status: empty output.")

        try:
            host = BootcHost.from_json(output)
        except tmt.utils.SpecificationError as error:
            raise tmt.utils.PrepareError("Failed to parse bootc status JSON.") from error

        if (status := host.status) is None:
            raise tmt.utils.PrepareError("Missing 'status' key in bootc output.")

        if (booted := status.booted) is None:
            raise tmt.utils.PrepareError("Missing 'booted' key in bootc status.")

        if (image_status := booted.image) is None:
            raise tmt.utils.PrepareError("Missing 'image' key in bootc booted entry.")

        return image_status.image.image

    def _get_base_containerfile_directives(self) -> list[str]:
        # In dry run mode, return an empty list because _get_current_bootc_image()
        # would fail - it executes a command on the guest. The build is skipped
        # anyway via the dry-run guard in build_container().
        if self.guest.is_dry_run:
            return []

        bootc_image = self._get_current_bootc_image()

        if bootc_image.startswith(LOCALHOST_BOOTC_IMAGE_PREFIX):
            return [f'FROM containers-storage:{bootc_image}']

        return [f'FROM {bootc_image}']

    def check_presence(self, *installables: Installable) -> ShellScript:
        return self.aux_engine.check_presence(*installables)

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        self.open_containerfile_directives()

        script = self.aux_engine.install(*installables, options=options)
        self.containerfile_directives.append(f'RUN {script}')
        return script

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        self.open_containerfile_directives()

        script = self.aux_engine.reinstall(*installables, options=options)
        self.containerfile_directives.append(f'RUN {script}')
        return script

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        self.open_containerfile_directives()

        script = self.aux_engine.install_debuginfo(*installables, options=options)
        self.containerfile_directives.append(f'RUN {script}')
        return script

    def refresh_metadata(self) -> ShellScript:
        self.open_containerfile_directives()

        script = self.aux_engine.refresh_metadata()
        self.containerfile_directives.append(f'RUN {script}')
        return script


# ignore[type-arg]: TypeVar in package manager registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_package_manager('bootc')  # type: ignore[arg-type]
class Bootc(PackageManager[BootcEngine]):
    NAME = 'bootc'

    _engine_class = BootcEngine

    # Invoke e.g. `bootc status`, and check if it returns "Booted image".
    probe_command = ShellScript(
        "type bootc && sudo bootc status && ((sudo bootc status --format yaml | grep -e 'booted: null' -e 'image: null') && exit 1 || exit 0)"  # noqa: E501
    ).to_shell_command()

    # Needs to be bigger than priorities of `yum`, `dnf`, `dnf5` and `rpm-ostree`.
    probe_priority = 130

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        script = self.engine.check_presence(*installables)

        try:
            output = self.guest.execute(script)
            stdout = output.stdout

        except RunError as exc:
            stdout = exc.stdout

        if stdout is None:
            raise GeneralError("rpm presence check provided no output")

        results: dict[Installable, bool] = {}

        for line, installable in zip(stdout.strip().splitlines(), installables):
            match = re.match(rf'package {re.escape(str(installable))} is not installed', line)
            if match is not None:
                results[installable] = False
                continue

            match = re.match(rf'no package provides {re.escape(str(installable))}', line)
            if match is not None:
                results[installable] = False
                continue

            results[installable] = True

        return results

    def build_container(self) -> None:
        # Skip in dry run mode
        if self.guest.is_dry_run:
            return

        if not self.engine.containerfile_directives:
            self.debug("No Containerfile directives to build container image, skipping build.")
            return

        image_tag = f"{LOCALHOST_BOOTC_IMAGE_PREFIX}/bootc/{uuid.uuid4()}"

        # Write the final Containerfile
        with self.guest.mkdtemp() as containerfile_dir:
            containerfile_path = Path(containerfile_dir, 'Containerfile')

            containerfile = '\n'.join(self.engine.containerfile_directives)

            base_image = self.engine._get_current_bootc_image()

            try:
                # First try if image is available in container registries.
                # Next try the local container storage.
                # As the last resort, copy the booted image to the local container storage.
                # Note that the last method will be used when `bootc` provision plugin
                # is used, where the container image is built on the machine running `tmt`.
                # We cannot use the last method by default because it does not preserve
                # all the container image layers, see
                # https://github.com/bootc-dev/bootc/issues/1259 for more information.
                self.guest.execute(
                    ShellScript(
                        f'{self.guest.facts.sudo_prefix} {tmt.utils.DEFAULT_SHELL} -c "('
                        f'  ( podman pull {base_image} || podman pull containers-storage:{base_image} )'  # noqa: E501
                        f'  || bootc image copy-to-storage --target {base_image}'
                        ')"'
                    )
                )
                self.guest.execute(
                    ShellScript(f'cat <<EOF > {containerfile_path!s} \n{containerfile} \nEOF')
                )

                self.debug(f"containerfile content: {containerfile}")
                # Build the container image
                self.info("package", "building container image with dependencies", "green")

                assert self.guest.parent is not None

                # Mount run_workdir so scripts have access to tmt files during build.
                # Use :Z for SELinux private label.
                self.guest.execute(
                    ShellScript(
                        f'{self.guest.facts.sudo_prefix} podman build -v {self.guest.run_workdir}:{self.guest.run_workdir}:Z -t {image_tag} -f {containerfile_path} {self.guest.run_workdir}'  # noqa: E501
                    )
                )

                # Switch to the new image for next boot
                self.info("package", f"switching to new image {image_tag}", "green")

                bootc_command, _ = self.engine.prepare_command()
                bootc_command += Command('switch', '--transport', 'containers-storage', image_tag)
                self.guest.execute(bootc_command)

                # Reboot into the new image
                self.info("package", "rebooting to apply new image", "green")
                self.guest.reboot()

            finally:
                # Reset containerfile directives
                self.engine.flush_containerfile_directives()

    def refresh_metadata(self) -> CommandOutput:
        self.engine.refresh_metadata()

        self.build_container()
        return CommandOutput(stdout=None, stderr=None)

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        presence = self.check_presence(*installables)

        missing_installables: set[Installable] = {
            installable for installable, present in presence.items() if not present
        }

        if missing_installables:
            self.engine.install(*missing_installables, options=options)
            self.build_container()

        return CommandOutput(stdout=None, stderr=None)

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        self.engine.reinstall(*installables, options=options)

        self.build_container()
        return CommandOutput(stdout=None, stderr=None)

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        self.engine.install_debuginfo(*installables, options=options)

        self.build_container()
        return CommandOutput(stdout=None, stderr=None)
