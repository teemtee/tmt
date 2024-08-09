import dataclasses
import re
from typing import TYPE_CHECKING, Any, Optional, cast

import tmt
import tmt.log
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.package_managers import Package
from tmt.result import PhaseResult
from tmt.steps.prepare import PreparePlugin
from tmt.steps.prepare.install import _RawPrepareInstallStepData
from tmt.steps.provision import Guest
from tmt.utils import Command, Path, ShellScript, field, uniq

if TYPE_CHECKING:
    import tmt.base
    import tmt.steps.discover
    import tmt.steps.prepare.install

PREPARE_WRAPPER_FILENAME = 'tmt-prepare-wrapper.sh'

FEDORA_BUILD_REQUIRES = [Package('@buildsys-build')]
RHEL_BUILD_REQUIRES = [Package('tar'),
                       Package('gcc-c++'),
                       Package('redhat-rpm-config'),
                       Package('redhat-release'),
                       Package('which'),
                       Package('xz'),
                       Package('sed'),
                       Package('make'),
                       Package('bzip2'),
                       Package('gzip'),
                       Package('gcc'),
                       Package('coreutils'),
                       Package('unzip'),
                       Package('diffutils'),
                       Package('cpio'),
                       Package('bash'),
                       Package('gawk'),
                       Package('info'),
                       Package('patch'),
                       Package('util-linux'),
                       Package('findutils'),
                       Package('grep')]


def insert_to_prepare_step(
        discover_plugin: 'tmt.steps.discover.DiscoverPlugin[Any]',
        sourcedir: Path,
        ) -> None:
    """ Single place to call when inserting PrepareDistGit from discover """

    prepare_step = discover_plugin.step.plan.prepare
    where = cast(tmt.steps.discover.DiscoverStepData, discover_plugin.data).where
    # Future install require
    data_require: _RawPrepareInstallStepData = {
        'how': 'install',
        'name': 'requires (dist-git)',
                'summary': 'Install required packages of tests detected by dist-git',
                'order': tmt.utils.DEFAULT_PLUGIN_ORDER_REQUIRES,
                'where': where,
                'package': []}
    future_requires: PreparePlugin[Any] = cast(
        PreparePlugin[Any], PreparePlugin.delegate(
            prepare_step, raw_data=data_require))
    prepare_step._phases.append(future_requires)

    # Future install recommend
    data_recommend: _RawPrepareInstallStepData = {
        'how': 'install',
        'name': 'recommends (dist-git)',
                'summary': 'Install recommended packages of tests detected by dist-git',
                'order': tmt.utils.DEFAULT_PLUGIN_ORDER_RECOMMENDS,
                'where': where,
                'package': [],
        'missing': 'skip'}
    future_recommends: PreparePlugin[Any] = cast(
        PreparePlugin[Any], PreparePlugin.delegate(
            prepare_step, raw_data=data_recommend))
    prepare_step._phases.append(future_recommends)

    prepare_step._phases.append(
        PrepareDistGit(
            step=prepare_step,
            data=DistGitData(
                where=where,
                source_dir=sourcedir,
                phase_name=discover_plugin.name,
                install_builddeps=discover_plugin.get('dist-git-install-builddeps'),
                require=discover_plugin.get('dist-git-require'),
                how='distgit',
                name="Prepare dist-git sources (buildrequires, patches, discovery...)",
                ),
            workdir=None,
            discover=discover_plugin,
            future_requires=future_requires,
            future_recommends=future_recommends,
            logger=discover_plugin._logger.descend(logger_name="extract-distgit", extra_shift=0)
            )
        )


@dataclasses.dataclass
class DistGitData(tmt.steps.prepare.PrepareStepData):
    source_dir: Optional[Path] = field(
        default=None,
        option='--source-dir',
        normalize=tmt.utils.normalize_path,
        exporter=lambda value: str(value) if isinstance(value, Path) else None,
        help="Path to the source directory where ``rpmbuild -bp`` should happen.",
        internal=True)
    phase_name: str = field(
        default_factory=str,
        option='--phase-name',
        help="Name of the discover step phase to inject tests to.",
        internal=True)
    order: int = 60
    install_builddeps: bool = field(
        default=False,
        option="--install-builddeps",
        is_flag=True,
        help="Install package build dependencies",
        )
    require: list['tmt.base.DependencySimple'] = field(
        default_factory=list,
        option="--require",
        metavar='PACKAGE',
        multiple=True,
        help='Additional required package(s) to be present before sources are prepared.',
        # *simple* requirements only
        normalize=lambda key_address, value, logger: tmt.base.assert_simple_dependencies(
            tmt.base.normalize_require(key_address, value, logger),
            "'require' can be simple packages only",
            logger),
        serialize=lambda packages: [package.to_spec() for package in packages],
        unserialize=lambda serialized: [
            tmt.base.DependencySimple.from_spec(package)
            for package in serialized
            ]
        )


# @tmt.steps.provides_method('distgit') Hiding from the menu
class PrepareDistGit(tmt.steps.prepare.PreparePlugin[DistGitData]):
    """
    Companion to the discover-dist-git, place where ``rpmbuild -bp`` happens

    Step is responsible:
    1. Install required packages for the rpmbuild itself
    2. Detect and install build requires
    3. Patch sources (rpmbuild -bp)
    4. Move patched sources from buildroot into TMT_SOURCE_DIR
    5. Call function of discover plugin to discover tests from TMT_SOURCE_DIR
    """

    _data_class = DistGitData

    def __init__(
        self,
        *,
        discover: Optional['tmt.steps.discover.DiscoverPlugin[Any]'] = None,
        future_requires: Optional['tmt.steps.prepare.PreparePlugin[Any]'] = None,
        future_recommends: Optional['tmt.steps.prepare.PreparePlugin[Any]'] = None,
            **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.discover = discover
        self.future_requires = future_requires
        self.future_recommends = future_recommends

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[PhaseResult]:
        """ Prepare the guests for building rpm sources """

        results = super().go(guest=guest, environment=environment, logger=logger)

        environment = environment or tmt.utils.Environment()

        # Packages required for this plugin to work and additional required packages
        explicit_requires = [Package(p) for p in self.get('require', [])] + [Package('rpm-build')]

        # Packages assumed to be present when building packages
        guest_distro = guest.facts.distro.lower() if guest.facts.distro else ""
        if "fedora" in guest_distro:
            explicit_requires += FEDORA_BUILD_REQUIRES
        elif "red hat" in guest_distro:
            explicit_requires += RHEL_BUILD_REQUIRES

        if self.get('install_builddeps'):
            # FIXME For now dnf only, ideally it will be capability of the package_manager...
            if "dnf" not in (guest.facts.package_manager or ''):
                raise tmt.utils.PrepareError("Cannot install build deps on system without dnf yet")
            explicit_requires += [Package('dnf-command(builddep)')]

        # Install required packages for rpm-build to work
        guest.package_manager.install(*explicit_requires)

        source_dir = self.data.source_dir
        assert source_dir

        try:
            spec_name = next(Path(source_dir).glob('*.spec')).name
        except StopIteration:
            raise tmt.utils.PrepareError(f"No '*.spec' file found in '{source_dir}'")

        content_before = set(source_dir.iterdir())

        dir_defines = [
            "--define", f'_sourcedir {source_dir}',
            "--define", f'_builddir {source_dir}',
            "--define", f'_srcrpmdir {source_dir}/SRPMS']

        if self.get('install_builddeps'):
            cmd = Command("rpmbuild", "-br", "--nodeps", spec_name, *dir_defines)
            try:
                stdout = guest.execute(command=cmd, cwd=source_dir).stdout
            except tmt.utils.RunError as error:
                # manpage says rpmbuild should return '11' for `-br --nodeps`
                # but it doesn't seem to be the case on f-39
                if error.returncode != 11:
                    raise tmt.utils.PrepareError("Unexpected return code of `rpmbuild -br` call.")
                stdout = error.stdout
            match = re.search(r'/SRPMS/(.*src.rpm)', stdout or '')
            if match:
                src_rpm_name = match.group(1)
            else:
                raise tmt.utils.PrepareError('No src.rpm file created by the `rpmbuild -br` call.')
            # Install build requires
            # Create the package manager command
            cmd, _ = guest.package_manager.prepare_command()
            # Can't set 'cwd' as the check for its existence fails for local workdir
            cmd += Command("builddep", "-y", f"SRPMS/{src_rpm_name}")
            guest.execute(command=cmd, cwd=Path(source_dir))

        # Finally run the rpm-build -bp
        cmd = Command(
            "rpmbuild", "-bp", spec_name, "--nodeps",
            *dir_defines
            )
        try:
            guest.execute(command=cmd,
                          cwd=source_dir,
                          )
        except tmt.utils.RunError as error:
            raise tmt.utils.PrepareError("Unable to 'rpmbuild -bp'.", causes=[error])

        # Workaround around new rpm behavior, https://github.com/teemtee/tmt/issues/2987
        # No hardcoded name, should keep working in the future
        cmd = Command(
            "rpmbuild",
            "-bc",
            "--short-circuit",
            "--nodeps",
            "--define",
            '__spec_build_pre echo tmt-get-builddir=%{_builddir}; exit 0',
            spec_name,
            *dir_defines)
        outcome = guest.execute(command=cmd, cwd=source_dir).stdout or ''
        match = re.search(r'tmt-get-builddir=(.+)', outcome)
        builddir = Path(match.group(1)) if match else None

        # But if the %build is missing in spec (e.g. in our test) the previous output was empty
        if builddir is None:
            guest.execute(command=ShellScript(
                "shopt -s dotglob; if test -e */SPECPARTS; then mv ./*-build/* .; else true; fi"),
                cwd=source_dir)
        elif builddir.resolve() != source_dir.resolve():
            guest.execute(command=ShellScript(f"shopt -s dotglob; mv {builddir}/* {source_dir}"))
        else:
            self.debug("Builddir matches source_dir, no need to copy anything.")

        # Make sure to pull back sources ...
        # FIXME -- Do we need to? Can be lot of data...
        guest.pull(source_dir)

        # Mark which file/dirs were created after rpmbuild ran
        content_after = set(source_dir.iterdir())
        created_content = [Path(p.name) for p in content_after - content_before]

        # When discover is set let it rediscover tests
        if self.discover is not None:
            self.discover.post_dist_git(created_content)
            # FIXME needs refactor of Prepare, tmt.base etc...
            # doing quick & dirty injection of prepareinstalls
            for g in self.step.plan.provision.guests():
                collected_requires: list[tmt.base.DependencySimple] = []
                collected_recommends: list[tmt.base.DependencySimple] = []
                for test in self.step.plan.discover.tests(enabled=True):
                    if not test.enabled_on_guest(g):
                        continue

                    collected_requires += tmt.base.assert_simple_dependencies(
                        test.require,
                        'After beakerlib processing, tests may have only simple requirements',
                        self._logger)

                    collected_recommends += tmt.base.assert_simple_dependencies(
                        test.recommend,
                        'After beakerlib processing, tests may have only simple requirements',
                        self._logger)

                    collected_requires += test.test_framework.get_requirements(
                        test,
                        self._logger)

                    for check in test.check:
                        collected_requires += check.plugin.essential_requires(
                            guest,
                            test,
                            self._logger)
                # Inject additional install plugins - require
                if collected_requires and self.future_requires:
                    self.future_requires.data.package = uniq(collected_requires)
                # Inject additional install plugins - recommend
                if collected_recommends and self.future_recommends:
                    self.future_recommends.data.package = uniq(collected_recommends)

        return results
