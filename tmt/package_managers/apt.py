import re
from typing import Optional, Union

import tmt.utils
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    Package,
    PackageManager,
    PackageManagerEngine,
    PackagePath,
    escape_installables,
    provides_package_manager,
)
from tmt.utils import (
    Command,
    CommandOutput,
    GeneralError,
    RunError,
    ShellScript,
)
from tmt.utils.templates import render_template

ReducedPackages = list[Union[Package, PackagePath]]


PRESENCE_TEMPLATE = """
set -x

export DEBIAN_FRONTEND=noninteractive

{% for installable in REAL_PACKAGES %}
echo "PRESENCE-TEST:{{ installable }}:{{ installable }}:$(dpkg-query --show {{ installable }})"
{% endfor %}

{% if FILESYSTEM_PATHS %}
  {% for installable in FILESYSTEM_PATHS %}
fs_path_package="$(apt-file search --package-only {{ installable }})"
if [ -z "$fs_path_package" ]; then
    echo "PRESENCE-TEST:{{ installable }}::"
else
    echo "PRESENCE-TEST:{{ installable }}:${fs_path_package}:$(dpkg-query --show $fs_path_package)"
fi
  {% endfor %}
{% endif %}
"""


INSTALL_TEMPLATE = """
set -x

export DEBIAN_FRONTEND=noninteractive

installable_packages="{{ REAL_PACKAGES | join(' ') }}"

{% if FILESYSTEM_PATHS %}
  {% for installable in FILESYSTEM_PATHS %}
fs_path_package="$(apt-file search --package-only {{ installable }})"
    {% if not OPTIONS.skip_missing %}
[ -z "$fs_path_package" ] && echo "No package found for path {{ installable }}" && exit 1
    {% endif %}
installable_packages="$installable_packages $fs_path_package"
  {% endfor %}
{% endif %}

{% if OPTIONS.check_first %}
dpkg-query --show $installable_packages \\
{% else -%}
/bin/false \\
{% endif -%}
{{ '||' if COMMAND == 'install' else '&&' }} {{ ENGINE.command.to_script() }} {{ COMMAND }} {{ ENGINE.options.to_script() }} {{ EXTRA_OPTIONS }} $installable_packages

{% if OPTIONS.skip_missing %}
exit 0
{% else %}
exit $?
{% endif %}
"""  # noqa: E501


class AptEngine(PackageManagerEngine):
    install_command = Command('install')

    _sudo_prefix: Command

    def prepare_command(self) -> tuple[Command, Command]:
        """
        Prepare installation command for apt
        """

        if self.guest.facts.is_superuser is False:
            self._sudo_prefix = Command('sudo')

        else:
            self._sudo_prefix = Command()

        command = Command()
        options = Command('-y')

        command += self._sudo_prefix
        command += Command('apt')

        return (command, options)

    def _enable_apt_file(self) -> ShellScript:
        return ShellScript(
            f'( {self.install(Package("apt-file"))} ) && {self._sudo_prefix} apt-file update'
        )

    def _reduce_to_packages(
        self, *installables: Installable
    ) -> tuple[list[Union[Package, PackagePath]], list[FileSystemPath]]:
        real_packages: list[Union[Package, PackagePath]] = []
        filesystem_paths: list[FileSystemPath] = []

        for installable in installables:
            if isinstance(installable, (Package, PackagePath)):
                real_packages.append(installable)

            elif isinstance(installable, FileSystemPath):
                filesystem_paths.append(installable)

            else:
                raise GeneralError(f"Package specification '{installable}' is not supported.")

        return (real_packages, filesystem_paths)

    def check_presence(self, *installables: Installable) -> ShellScript:
        real_packages, filesystem_paths = self._reduce_to_packages(*installables)

        if filesystem_paths:
            return self._enable_apt_file() + ShellScript(
                render_template(
                    PRESENCE_TEMPLATE,
                    ENGINE=self,
                    REAL_PACKAGES=escape_installables(*real_packages),
                    FILESYSTEM_PATHS=escape_installables(*filesystem_paths),
                )
            )

        return ShellScript(
            render_template(
                PRESENCE_TEMPLATE,
                ENGINE=self,
                REAL_PACKAGES=escape_installables(*real_packages),
                FILESYSTEM_PATHS=escape_installables(*filesystem_paths),
            )
        )

    def _extra_options(self, options: Options) -> Command:
        extra_options = Command()

        if options.skip_missing:
            extra_options += Command('--ignore-missing')

        return extra_options

    def refresh_metadata(self) -> ShellScript:
        return ShellScript(
            f'export DEBIAN_FRONTEND=noninteractive; {self.command.to_script()} update'
        )

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        options = options or Options()
        extra_options = self._extra_options(options)

        real_packages, filesystem_paths = self._reduce_to_packages(*installables)

        if filesystem_paths:
            return self._enable_apt_file() & ShellScript(
                render_template(
                    INSTALL_TEMPLATE,
                    ENGINE=self,
                    COMMAND='install',
                    OPTIONS=options,
                    EXTRA_OPTIONS=extra_options,
                    REAL_PACKAGES=escape_installables(*real_packages),
                    FILESYSTEM_PATHS=escape_installables(*filesystem_paths),
                )
            )

        return ShellScript(
            render_template(
                INSTALL_TEMPLATE,
                ENGINE=self,
                COMMAND='install',
                OPTIONS=options,
                EXTRA_OPTIONS=extra_options,
                REAL_PACKAGES=escape_installables(*real_packages),
                FILESYSTEM_PATHS=escape_installables(*filesystem_paths),
            )
        )

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        options = options or Options()
        extra_options = self._extra_options(options)

        real_packages, filesystem_paths = self._reduce_to_packages(*installables)

        if filesystem_paths:
            return self._enable_apt_file() & ShellScript(
                render_template(
                    INSTALL_TEMPLATE,
                    ENGINE=self,
                    COMMAND='reinstall',
                    OPTIONS=options,
                    EXTRA_OPTIONS=extra_options,
                    REAL_PACKAGES=escape_installables(*real_packages),
                    FILESYSTEM_PATHS=escape_installables(*filesystem_paths),
                )
            )

        return ShellScript(
            render_template(
                INSTALL_TEMPLATE,
                ENGINE=self,
                COMMAND='reinstall',
                OPTIONS=options,
                EXTRA_OPTIONS=extra_options,
                REAL_PACKAGES=real_packages,
                FILESYSTEM_PATHS=filesystem_paths,
            )
        )

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        raise tmt.utils.GeneralError("There is no support for debuginfo packages in apt.")


@provides_package_manager('apt')
class Apt(PackageManager[AptEngine]):
    NAME = 'apt'

    _engine_class = AptEngine

    probe_command = Command('apt', '--version')

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        presence_script = self.engine.check_presence(*installables)

        try:
            output = self.guest.execute(presence_script)
            stdout, stderr = output.stdout, output.stderr

        except RunError as exc:
            stdout, stderr = exc.stdout, exc.stderr

        if stdout is None or stderr is None:
            raise GeneralError("apt presence check provided no output")

        results: dict[Installable, bool] = {}

        for installable in installables:
            results[installable] = False

            match = re.search(
                rf'(?m)^PRESENCE-TEST:{"".join(escape_installables(installable))}:.*?:(.*?)$',
                stdout,
            )

            if match is None:
                continue

            if match.group(1):
                results[installable] = True

        return results

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        raise tmt.utils.GeneralError("There is no support for debuginfo packages in apt.")
