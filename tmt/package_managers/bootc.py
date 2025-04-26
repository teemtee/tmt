import json
import re
import uuid
from typing import Any, Optional, cast

import tmt.utils
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    PackageManager,
    PackageManagerEngine,
    dnf,
    provides_package_manager,
)
from tmt.utils import Command, CommandOutput, GeneralError, Path, RunError, ShellScript


class BootcEngine(PackageManagerEngine):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize bootc engine for package management"""
        super().__init__(*args, **kwargs)

        self.aux_engine = dnf.DnfEngine(*args, **kwargs)

        self.initialize_containerfile_directives()

    def initialize_containerfile_directives(self) -> None:
        """Initialize containerfile directives"""
        self.containerfile_directives = self._get_base_containerfile_directives()

    def prepare_command(self) -> tuple[Command, Command]:
        """
        Prepare installation command for bootc
        """
        command = Command()

        if self.guest.facts.is_superuser is False:
            command += Command('sudo')

        command += Command('bootc')
        return (command, Command(''))

    def _get_current_bootc_image(self) -> str:
        """Get the current bootc image running on the system"""

        command, _ = self.prepare_command()
        command += Command('status', '--json')
        output = self.guest.execute(command, silent=True)

        if not output.stdout:
            raise tmt.utils.PrepareError("Failed to get current bootc status: empty output.")

        try:
            image_status = json.loads(output.stdout)
        except json.JSONDecodeError as error:
            raise tmt.utils.PrepareError(f"Failed to parse bootc status JSON: {error}")

        if not image_status:
            raise tmt.utils.PrepareError("Failed to get current bootc status: empty JSON.")

        # Extract nested information with clear error messages for each missing key
        try:
            booted = image_status.get('status', {}).get('booted', {})
            if not booted:
                raise KeyError("'booted' key")

            image_info = booted.get('image')
            if not image_info:
                raise KeyError("'image' key in booted status")

            image_data = image_info.get('image', {})

            base_image = cast(str, image_data.get('image', ''))
            if not base_image:
                raise KeyError("'image' name in image data")

            return base_image
        except KeyError as error:
            raise tmt.utils.PrepareError(f"Failed to extract bootc image info: missing {error}")

    def _get_base_containerfile_directives(self) -> list[str]:
        return [f'FROM containers-storage:{self._get_current_bootc_image()}']

    def check_presence(self, *installables: Installable) -> ShellScript:
        script = self.aux_engine.check_presence(*installables)
        self.containerfile_directives.append(f'RUN {script}')
        return script

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        script = self.aux_engine.install(*installables, options=options)
        self.containerfile_directives.append(f'RUN {script}')
        return script

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        script = self.aux_engine.reinstall(*installables, options=options)
        self.containerfile_directives.append(f'RUN {script}')
        return script

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        script = self.aux_engine.install_debuginfo(*installables, options=options)
        self.containerfile_directives.append(f'RUN {script}')
        return script

    def refresh_metadata(self) -> ShellScript:
        script = self.aux_engine.refresh_metadata()
        self.containerfile_directives.append(f'RUN {script}')
        return script


@provides_package_manager('bootc')
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

        if len(installables) == 1 and isinstance(installables[0], FileSystemPath):
            try:
                self.guest.execute(script)

            except RunError as exc:
                if exc.returncode == 1:
                    return {installables[0]: False}

                raise exc

            return {installables[0]: True}

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
        image_tag = f"localhost/tmt/bootc/{uuid.uuid4()}"

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
                        f'( podman pull {base_image} || podman pull containers-storage:{base_image} ) || bootc image copy-to-storage --target {base_image}'  # noqa: E501
                    )
                )
                self.guest.execute(
                    ShellScript(f'cat <<EOF > {containerfile_path!s} \n{containerfile} \nEOF')
                )

                self.debug(f"containerfile content: {containerfile}")
                # Build the container image
                self.info("package", "building container image with dependencies", "green")
                self.guest.execute(
                    Command('podman', 'build', '-t', image_tag, '-f', str(containerfile_path), '.')
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
                # Re-initialize containerfile directives
                self.engine.initialize_containerfile_directives()

    def refresh_metadata(self) -> CommandOutput:
        self.engine.refresh_metadata()

        self.build_container()
        return CommandOutput(stdout=None, stderr=None)

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        self.engine.install(*installables, options=options)

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
