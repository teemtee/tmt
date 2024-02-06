Name:           tmt
Version:        1.31.0
Release:        %autorelease
Summary:        Test Management Tool

License:        MIT
URL:            https://github.com/teemtee/tmt
Source0:        %{pypi_source tmt}

BuildArch:      noarch
BuildRequires:  python3-devel

Requires:       git-core rsync sshpass

Obsoletes:      python3-tmt < %{version}-%{release}
Obsoletes:      tmt-report-html < %{version}-%{release}
Obsoletes:      tmt-report-junit < %{version}-%{release}
Obsoletes:      tmt-report-polarion < %{version}-%{release}
Obsoletes:      tmt-report-reportportal < %{version}-%{release}

Recommends:     bash-completion

%define workdir_root /var/tmp/tmt

%py_provides    python3-tmt

%description
The tmt Python module and command line tool implement the test
metadata specification (L1 and L2) and allows easy test execution.

%pyproject_extras_subpkg -n tmt export-polarion
%pyproject_extras_subpkg -n tmt report-junit
%pyproject_extras_subpkg -n tmt report-polarion

%package -n     tmt+test-convert
Summary:        Dependencies required for tmt test import and export
Obsoletes:      tmt-test-convert < %{version}-%{release}
Requires:       tmt == %{version}-%{release}
Requires:       make
Requires:       python3-bugzilla
Requires:       python3-nitrate
Requires:       python3-html2text
Requires:       python3-markdown

%description -n tmt+test-convert
This is a metapackage bringing in extra dependencies for tmt.
It contains no code, just makes sure the dependencies are installed.

%package -n     tmt+provision-container
Summary:        Dependencies required for tmt container provisioner
Obsoletes:      tmt-provision-container < %{version}-%{release}
Obsoletes:      tmt-container < 0.17
Requires:       tmt == %{version}-%{release}
Requires:       podman
Requires:       (ansible or ansible-collection-containers-podman)

%description -n tmt+provision-container
This is a metapackage bringing in extra dependencies for tmt.
It contains no code, just makes sure the dependencies are installed.

%package -n     tmt+provision-virtual
Summary:        Dependencies required for tmt virtual machine provisioner
Obsoletes:      tmt-provision-virtual < %{version}-%{release}
Obsoletes:      tmt-testcloud < 0.17
Requires:       tmt == %{version}-%{release}
Requires:       python3-testcloud >= 0.9.10
Requires:       libvirt-daemon-config-network
Requires:       openssh-clients
Requires:       (ansible or ansible-core)
# Recommend qemu system emulators for supported arches
Recommends:     qemu-kvm-core
%if 0%{?fedora}
Recommends:     qemu-system-aarch64-core
Recommends:     qemu-system-ppc-core
Recommends:     qemu-system-s390x-core
Recommends:     qemu-system-x86-core
%endif

%description -n tmt+provision-virtual
This is a metapackage bringing in extra dependencies for tmt.
It contains no code, just makes sure the dependencies are installed.

%package -n     tmt+provision-beaker
Summary:        Dependencies required for tmt beaker provisioner
Provides:       tmt-provision-beaker == %{version}-%{release}
Obsoletes:      tmt-provision-beaker < %{version}-%{release}
Requires:       tmt == %{version}-%{release}
Requires:       python3-mrack-beaker

%description -n tmt+provision-beaker
This is a metapackage bringing in extra dependencies for tmt.
It contains no code, just makes sure the dependencies are installed.

# Replace with pyproject_extras_subpkg at some point
%package -n     tmt+all
Summary:        Extra dependencies for the Test Management Tool
Provides:       tmt-all == %{version}-%{release}
Obsoletes:      tmt-all < %{version}-%{release}
Requires:       tmt+test-convert == %{version}-%{release}
Requires:       tmt+export-polarion == %{version}-%{release}
Requires:       tmt+provision-container == %{version}-%{release}
Requires:       tmt+provision-virtual == %{version}-%{release}
Requires:       tmt+provision-beaker == %{version}-%{release}
Requires:       tmt+report-junit == %{version}-%{release}
Requires:       tmt+report-polarion == %{version}-%{release}

%description -n tmt+all
All extra dependencies of the Test Management Tool. Install this
package to have all available plugins ready for testing.

%prep
%autosetup -p1 -n tmt-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
export SETUPTOOLS_SCM_PRETEND_VERSION=%{version}
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files tmt

mkdir -p %{buildroot}%{_mandir}/man1
install -pm 644 tmt.1 %{buildroot}%{_mandir}/man1
mkdir -p %{buildroot}%{_datadir}/bash-completion/completions
install -pm 644 completions/bash/%{name} %{buildroot}%{_datadir}/bash-completion/completions/%{name}
mkdir -pm 1777 %{buildroot}%{workdir_root}
mkdir -p %{buildroot}/etc/%{name}/
install -pm 644 %{name}/steps/provision/mrack/mrack* %{buildroot}/etc/%{name}/

%check
%pyproject_check_import

%files -n tmt -f %{pyproject_files}
%doc README.rst examples
%{_bindir}/tmt
%{_mandir}/man1/tmt.1.gz
%dir %{workdir_root}
%{_datadir}/bash-completion/completions/%{name}

%files -n tmt+provision-container -f %{_pyproject_ghost_distinfo}
%files -n tmt+provision-virtual -f %{_pyproject_ghost_distinfo}
%files -n tmt+test-convert -f %{_pyproject_ghost_distinfo}
%files -n tmt+provision-beaker -f %{_pyproject_ghost_distinfo}
%config(noreplace) %{_sysconfdir}/%{name}/mrack*
%files -n tmt+all -f %{_pyproject_ghost_distinfo}

%changelog
* Tue Feb 06 2024 Michal Hlavinka <mhlavink@redhat.com> - 1.31.0
- Simple ReST renderer for CLI help texts (#2574)
- Generate plugin documentation from their sources (#2549)
- Fix environment from command line updated twice (#2614)
- Introduce a new prepare plugin for common features (#2198)
- Remove `xfail` for the `multidict` issue on `rawhide`
- Prevent catching avc denials from previous tests
- Remove an obsolete workaround for `centos-stream-8`
- Enable the `/tests/discover/libraries` test (#2222)
- Add documentation on tmt & regular expressions
- Fix expansion of envvar starting with `@` in fmf nodes
- Add the `zcrypt` adapter specification
- Allow urllib3 2.x
- Enable `/plans/provision/virtual` for pull requests (#2558)
- Remove the dns failures workaround
- Fix reporting of schema errors without the `$id` key
- AVC check now saves a timestamp on guest instead of using runner's time
- Add check to prevent `tmt try` deleting imported libraries
- Reduce usage of locks in the `testcloud` plugin
- Add support for envvars import and export to Polarion
- Use enumeration to implement action handling
- Handle the `ctrl-d` shortcut in `tmt try`
- Run tests with `interactive` mode during `tmt try`
- Fix `tmt import --dry` and Polarion import file name
- Document that `name` is supported in `--filter` search (#2637)
- Refactor running of interactive commands (#2554)
- Create container images from the latest non-dev copr build
- Fail `dmesg` check if it contains `Call Trace` or `segfault`
- Mention the reboot timeout variable in the release notes
- Bump the default reboot timeout to 10 minutes
- Allow change of the default reboot timeout via environment variable
- Introduce essential requirements
- Allow `--update-missing` to change the default `how` value
- Document the new `become` feature
- Raise an error when loading pre-1.24 `tests.yaml`
- Support terminating process running test via its test invocation (#2589)
- Fix `egrep` warning in `/plans/install/docs`
- Test framework may provide additional test requirements
- Improve logging of AVC check plugin and its test
- Cleanup logging in `tmt.utils.create_file()`
- Drop connection closed messages from test output
- Recommend `qemu-kvm-core` for `provision-virtual`
- Fix `/tests/plan/import` to not use special ref (#2627)
- Improve imported plan modification test to verify the order as well (#2618)
- Retry the `git clone` action multiple times
- Simplify the debuginfo installation test
- Support `virtualization.is-virtualized` in `mrack` plugin
- Support running all or selected steps `--again`
- Allow hardware requirements limit acceptable operators
- Fix inheritance of some keys in provision step data
- Run a callback when command process starts
- Add support for hard reboot to Beaker provision plugin
- Make collected requires/recommends guest-aware
- Copy top level `main.fmf` during testdir pruning
- Add support for Artemis API v0.0.67
- Add support for `cpu.flag` hardware requirement
- Use a different pidfile location for the full test
- Clear test invocation data path use and derived paths
- Add support for disallowing plugins via command line
- Use constraint classes specific for particular value type
- Making rhts metric value optional.
- Ignore tarballs and generated man page
- Cover `tmt.libraries` with `pyright` checks
- Parallelize the `provision` step
- Let `click` know about the maximal output width
- Cover `tmt.identifier` with `pyright` checks
- Extend `duration` of `/tests/core/escaping` a bit
- Move docs templates into their own directory
- Drop no longer needed `tmt.utils.copytree()`
- Drop no longer used `tmt.utils.listify()`
- Provision plugins use `self.data` instead of `self.get()`
- Prepare and finish plugins use self.data instead of self.get()
- Fix tmt.utils.format to allow int and float values
- Move code-related pages under new `code` directory
- Warn on test case not found in Polarion during report
- Bump pre-commit linters
- When cloning a logger, give it its own copy of labels
- Add a `Toolbelt Catalog` entry for `tmt`
- Enable the `avc` check for all `tmt` tests
- Fix dmesg check test on Fedora rawhide & newer

* Fri Dec 08 2023 Petr Šplíchal <psplicha@redhat.com> - 1.30.0
- Make `arch` field unsupported in the spec
- Introduce `tty` test attribute to control terminal environment
- Ensure the imported plan's `enabled` key is respected
- Add support for user defined templates (#2519)
- Update the common schema for the `check` key
- Create a `checks` directory to store avc/dmesg checks
- Correctly update environment from importing plan
- Implement `tmt try` for interactive sessions
- Use a shorter time for `podman stop` (#2480)
- Add the `redis` server as a multihost sync example
- Improve documentation of test checks
- Adjust the format of Polarion test run title
- Run all available tests only upon a user request
- Rename `name` to `how` in test check specification (#2527)
- Link `inheritance` and `elasticity` from the guide
- Add the `fips` field for the `polarion` report
- Cover `tmt.cli` with `pyright` (#2520)
- Custom soft/hard reboot commands for the connect provision plugin
- Add `--feeling-safe` for allowing possibly dangerous actions
- Update docs for the `polarion` report plugin
- Move test-requested reboot handling into test invocation class
- Add `-i` to select an image in beaker and artemis
- Document how to use `yaml` anchors and aliases
- Simplify log decolorizers to support pickleable trees
- Add description field to polarion report plugin
- Make check plugin class generic over check class (#2502)
- Increase verbosity of Artemis provisioning errors
- Add more distros to the `mrack` config
- Move the `contact` key to the `Core` class
- Bump tmt in lint pre-commit check to 1.29.0
- Add Python 3.12 to the test matrix
- Move `mrack` configs into `tmt+provision-beaker`
- Allow running upgrade from the current repository
- Fix remote nested library fetch and add test
- Cover tmt.options with pyright
- Cover tmt.checks, tmt.frameworks and tmt.log with pyright
- Cover tmt.result with pyright checks
- Store fmf `context` in results for each test
- Add networks to the podman provision plugin (#2419)
- Add a dedicated exit code when all tests reported `skip` result
- Move invocation-related fields out of `Test` class
- Remove expected fail from `/tests/pip/install/full`
- Convert test execution internals to use "invocation" bundle (#2469)
- Introduce a separate page `Code` for code docs
- Add code documentation generated from docstrings
- Fix possible unbound variable after import-under-try
- Add `pyright` as a `pre-commit` check
- Add a helper for nonconflicting, multihost-safe filenames
- Add the `whiteboard` option for `beaker` provision
- Support timestamped logging even on the terminal
- Enable pyupgrade `UP` ruff rule
- Fix `UP035` deprecated-import violations
- Fix `UP034` extraneous-parentheses violation
- Fix `UP033` lru-cache-with-maxsize-none violations
- Fix `UP032` f-string violations
- Fix `UP013` convert-typed-dict-functional-to-class
- Fix `UP009` utf8-encoding-declaration violations
- Fix `UP006` non-pep585-annotation violations
- Try several times to build the `become` container (#2467)
- Add .py file extension to docs scripts (#2476)
- Add a link to the Testing Farm documentation
- Use `renku` as the default theme for building docs
- Properly normalize the test `path` key
- Add an `adjust` example for enabling custom repo
- Drop special normalization methods
- Disable `dist-git-init` in the `distgit` test (#2463)

* Mon Nov 06 2023 Lukáš Zachar <lzachar@redhat.com> - 1.29.0
- Add page `Releases` to highlight important changes
- Update and polish hardware requirement docs
- Refactor generating of stories and lint check docs
- Add support for pruning test directories
- Download all sources for `dist-git-source`
- Source plan environment variables after `prepare` and `execute` steps
- Framework is not consulted on results provided by tmt-report-result
- Run scripts with `sudo` when `become` is on
- Add `retry` for pulling images in the `podman` plugin
- Add hardware schema for GPU
- Change the default test pidfile directory to `/var/tmp`
- Add `device` key into the `hardware` specification
- Update code and test coverage for the `check` key
- Document case-insensitive context dimension values
- Fix use of the `-name` suffix in system HW requirement
- Correct parsing when called as `rhts`
- Reconcile HW requirements with virtual's own options
- Move the `README` content into `docs/overview`
- Make `BasePlugin` generic over step data class
- Use `UpdatableMessage` for execute/internal progress bar
- Drop an empty line from the pull request template
- Add `runner` property to run with test runner facts
- Export sources of an `fmf` node
- Bump pre-commit linters to newer versions
- Append the checklist template to new pull requests
- Extend tmt-reboot to allow reboot from outside of the test process
- Allow optional doc themes
- Use consistent style for multiword test names
- Show `check` results in the `html` report
- Update `where` implementation, docs & test coverage (#2411)
- Document difference between key, field and option
- Rename multiword keys to use dashes in export and serialization
- Allow Path instance to be used when constructing commands
- Switch `Logger.print()` to output to stdout
- Replace Generator type annotation with Iterator (#2405)
- Refactor data container helpers
- When merging fmf and CLI, use shared base step data
- Fix installing package from the command line
- Add support for checks to have their data packages
- Switch `tmt.identifier` from using `fmf.log`
- Hide test/plan/story internal fields from export
- Fix full test suite after recent packaging changes
- Update the list of code owners
- Include the `fmf` root in the tarball as well

* Wed Oct 11 2023 Petr Šplíchal <psplicha@redhat.com> - 1.28.2
- Build man page during the `release` action

* Wed Oct 11 2023 Petr Šplíchal <psplicha@redhat.com> - 1.28.1
- Remove the `.dev0` suffix from the spec `Version`

* Fri Oct 06 2023 Petr Šplíchal <psplicha@redhat.com> - 1.28.0
- Update the `release` action with `hatch` changes
- Fix the multihost web test to work with container
- Add `skip` as a supported custom result outcome
- Add docs for the new `--update-missing` option
- Remove irrelevant mention of `rhel-8` in the spec
- Record start/end time & duration of test checks
- Add `--update-missing` to update phase fields only when not set by fmf
- Add --skip-prepare-verify-ssh and --post-install-script to artemis plugin (#2347)
- Force tmt-link pre-commit to use fmf 1.3.0 which brings new features (#2376)
- Add logging of applied adjust rules
- Handle all context dimension values case insensitive
- Hide `OPTIONLESS_FIELDS` from `tmt plan show`
- Add context into the `html` report
- Display test check results in `display` report output
- Fix creation of guest data from plugin options
- Allow wider output
- Beaker plugin is negating Beaker operators by default
- Include link to the data directory in the html report
- Teach logging methods to handle common types
- Move the copr repository to the `teemtee` group
- Add a new `cpu` property `stepping` to hardware
- Extract beakerlib phase name to a failure log
- Always show the real beaker job id
- Create a production copr build for each release
- AVC denials check for tests (#2331)
- Add nice & colorfull help to "make" targets
- Include more dependencies in the dev environment
- Stop using the `_version.py` file
- Replace `opt()` for `--dry/--force` with properties
- Update build names for copr/main and pull requests
- Use `hatch` and `pyproject`, refactor `tmt.spec`
- Use dataclass for log record details instead of typed dict
- Refactor html report plugin to use existing template rendering
- Narrow type of hardware constraint variants
- Refactor parameters of `Plan._iter_steps()`
- Use `format_value()` instead of `pprint()`
- Use the minimal plan to test imported plan execution
- Refactor exception rendering to use generators
- Add the `export` callback for fields (#2288)
- Update a verified-by link for the beaker provision
- Multi-string help texts converted to multiline strings
- Make the upload to PyPI working again
- Hide command event debug logs behind a log topic (#2281)
- Replace `pkg_resources` with `importlib.resources`
- Wrap `click.Choice` use with `choices` parameter
- Lower unnecessary verbosity of podman commands
- Move check-related code into `tmt.checks`
- Disable `systemd-resolved` to prevent dns failures
- Adjust test coverage for deep beakerlib libraries
- Document migration from provision.fmf to tmt (#2325)
- Remove TBD of initiator context for Packit
- Fix output indentation of imported plans
- Copr repo with a group owner requires quotes

* Wed Sep 06 2023 Petr Šplíchal <psplicha@redhat.com> - 1.27.0-1
- Use `testcloud` domain API v2
- Bootstrap before/after test checks (#2210)
- Separate value formatting from key/value nature of tmt.utils.format()
- Render `link` fields in tmt stories and specs
- Render default friendly command for guest execution
- Use consistently plural/singular forms in docs
- Make file/fmf dependencies hashable
- Rewrite git url for discover fmf: modified-only
- Refactor Artemis and Beaker provision tests to make room for HW
- Adjust imported plan to let its adjust rules make changes
- Get Ansible logging on par with general command execution
- Support Click versions newer than 8.1.4
- Teach tmt test create to link relevant issues (#2273)
- Add story describing CLI for multiple phases
- When rendering exception, indetation was dropping empty lines
- Expose tmt version as an environment variable
- Fix handling of integers and hostname in Beaker plugin
- Fix bug where polarion component is misinterpreted as list
- Refactor recording of CLI subcommand invocations (#2188)
- Put `--help` at the end of the CLI in the step usage
- Extend the expected `pip install` fail to `f-39`
- Make `tmt init` add .fmf directory into git index
- Fix guest data show() and how it displays hardware requirements
- Add lint check for matching guests, roles and where keys
- Add -e/--environment/--environment-files to plan show/export
- No more need to install `pre-commit` using `pip`
- Ensure that step phases have unique names
- Verbose regular expression for linter descriptions
- Initial draft of hardware requirement helpers
- Simplify the reportportal plugin test using `yq`
- Add dynamic ref support to library type dependency
- Remove `epel-8` and `python-3.6` specifics
- Use the latest `sphinx-rtd-theme` for docs building
- Full `pip install` expected to fail on `Rawhide`
- Add missing name attribute to report plugins schema
- Add missing arguments in polarion report schema
- Extend sufficiently the full test suite duration
- Add support for log types to Artemis plugin
- Fix `tmt run --follow`, add test coverage for it
- Remove the temporary hotfix for deep libraries

* Mon Jul 31 2023 Lukáš Zachar <lzachar@redhat.com> - 1.26.0
- Do not throw an exception on missing mrack.log
- Allow injecting credentials for git clone
- Exception in web_link() when node root is missing
- Rewrite url in git_clone
- Add support for rendering error tracebacks
- ReST export plugin should accept --template option
- Add `role` to the Beaker provision plugin schema
- Fix test checking custom destination for libraries
- Create plans to cover individual step features (#2216)
- Add cache_property for things that are generated but not often
- Simplify public git conversion with a declarative list
- Spec-based container becomes generic over input/output specs
- Clean up logging in `tmt.utils.create_directory()`
- Move test framework code into distinct framework classes
- Add template option to polarion report
- Group discover/fmf options, improve wording a bit
- Record tmt command line in tmt log
- Add note about dynamic ref to the plan import spec
- Use the `Deprecated` class for deprecated options
- Remove `python3-mrack-beaker` from `BuildRequires`
- Switch discover/fmf to our field() implementation
- Lock the `click` version < 8.1.4
- Refine examples of plans > discover > fmf
- Override packit actions for `propose_downstream`

* Mon Jul 10 2023 Lukáš Zachar <lzachar@redhat.com> - 1.25.0
- Test for pruning needs VM
- Internal anonymous git:// access is deprecated
- Beakerlibs pruning and merge
- Add dynamic ref evaluation support to plan import
- Replace self.opt() when looking for debug/verbose/quiet setting
- Reimplement the `ReportPortal` plugin using API
- Make `Step` class own export of step data (#2040)
- Make relevancy/coverage linters to not re-read fmf files
- Add a single `tmpdir` fixture for all Python versions
- Replace named tuples with data classes
- Replace `/` in safe name, and fix prepare step to use safe names
- Do not export fmf id's ref when it's the default branch
- Move the sync libraries into a separate section
- Allow running next plan in queue when one fails to complete
- Fix a too strict check for the detected library
- Convert provision plugins' step data to our field implementation
- Convert execute plugins to `tmt.utils.field()` for options
- Cache that beakerlib/library repo is missing
- Use code-block directive for examples and code blocks
- Add the `show()` method for guest data packages
- Turn fmf context into a fancy dict
- Enable ruff checks for mutable dataclass field defaults
- Create option metavar from listed choices
- Document how to modify imported plans
- Recommend needs a different option for `dnf5`
- Ask ruff to show what it fixed
- Bumps supported Artemis API to 0.0.58
- Use `--version` to gather the package_manager fact
- Use f-strings where possible
- Bump pre-commit hooks to latest version
- Fix ruff RUF010: Use f-strings conversion flags
- Fix py<38 mypy type:ignore being on wrong line
- Move isort to ruff
- Enable passing Pylint checks
- Fix ruff RSE102: Unnecessary parentheses on exception
- Fix ruff PIE: flake8-pie errors
- Remove duplicates from ruff rules selection
- Fix ruff SIM: flake8-simplify errors
- Fix ruff RET: flake8-return errors
- Fix ruff PT: flake8-pytest-style errors
- Fix ruff UP: pyupgrade errors
- Fix ruff N: pep8-naming errors
- Fix ruff RUF005: collection-literal-concatenation
- Fix ruff B: flake8-bugbear errors
- Fix flake8 C405: unnecessary literal set
- Fix flake8 C401: unnecessary generator set
- Fix flake8 C416: unnecessary comprehension
- Fix flake8 C408: unnecessary collection calls
- Polarion report set to UTC timezone
- Add `Organize Data` as a new tmt guide chapter
- Fix emptiness check of /var/tmp/tmt in /tests/status/base
- Allow modification of imported plans
- Raise error if malformed test metadata is given
- Ensure test with empty custom results ends as an ERROR
- Fix /tests/status/base when /var/tmp/tmt is empty
- Remove `pytest.ini` from the `Makefile` targets
- Bad source path for local libraries file require
- Remove useless loop.cycle() from the HTML report
- Implement basic filtering for the HTML report
- Cleanup of "logging function" types
- Do not patch verbosity in discover for --fmf-id
- Drop enum from HW hypervisor and boot method constraints
- Fix enforcement of workdir root in full workdir root test
- Narrow type of file & library dependencies
- Make web-link test play nicely with custom SSH host config
- Use serialization callbacks for last script fields
- Save click context in click context object
- Add the `envvar` argument to `utils.field()`
- Improve structure of the packit config a bit
- Update release instructions with simplified steps
- Sync changelog when creating downstream release

* Fri Jun 09 2023 Petr Šplíchal <psplicha@redhat.com> - 1.24.1-1
- Revert the `Source0` url to the original value
- Use correct url for the release archive, fix docs

* Wed Jun 07 2023 Petr Šplíchal <psplicha@redhat.com> - 1.24.0-1
- Do not display guest facts when showing a plan
- Add new guide/summary for multihost testing
- Define a "plugin registry" class
- Hide `facts` in the `virtual` provision plugin
- Cache resolved linters
- Improve documentation of lint checks (#2089)
- A custom wrapper for options instead of click.option()
- Identify incorrect subcommand after a correct one
- Remove one extra space between @ and decorator name
- Assign envvars to Polarion report arguments
- Expose "key address" to normalization callbacks (#1869)
- Move export of special test/plan/story fields to their respective classes
- Expose guest topology to tests and scripts (#2072)
- Enable building downstream release using Packit
- Add sections for environment variable groups
- Add default envvar to plugin options
- Load env TMT_WORKDIR_ROOT when running tmt status (#2087)
- Opportunistically use "selectable" entry_points.
- Explicitly convert tmpdir to str in test_utils.py.
- Move pytest.ini contents to pyproject.toml.
- Rename Require* classes to Dependency* (#2099)
- Expose fmf ID of tests in results
- Use the `tmt-lint` pre-commit hook
- Turn finish step implementation to queue-based one (#2110)
- Convert base classes to data classes (#2080)
- Crashed prepare and execute steps propagate all causes
- Support exceptions with multiple causes
- Make "needs sudo" a guest fact (#2096)
- Test data path must use safe guest/test names
- Support for multi case import from Polarion and Polarion as only source (#2084)
- Fix search function in docs
- Make tmt test wrapper name unique to avoid race conditions
- Change link-polarion argument default to false
- Add export plugin for JSON (#2058)
- Handle el6 as a legacy os too in virtual provision
- Hint beakerlib is old when result parsing fails
- Revert "Fix dry mode handling when running a remote plan"
- Set a new dict instance to the Plan class
- Replaces "common" object with logger in method hint logging
- Parallelize prepare and execute steps
- Formalizing guest "facts" storage
- Support urllib3 2.x and its allowed_methods/method_whitelist
- Require setuptools

* Thu May 11 2023 Lukáš Zachar <lzachar@redhat.com> - 1.23.0-1
- Add `Artemis` to the `provision` documentation
- Add artemis's user defined watchdog specification
- Add support for require of files and directories
- Expose test serial number as an environment variable
- Print only failed objects when linting in hook
- Refactored metadata linting
- Request newer os image and python version for docs
- Explore all available plugins only once
- Add test start/end timestamps into results
- Implement `deprecated` for obsoleted options
- Unify results examples in test and plan specification
- Convert gitlab private namespace into dist-git url
- Shorter Nitrate summary name
- Correct the path of Ansible playbook
- Refactor logging during plugin discovery, using tmt's logging
- Improve names and docs around CLI context in Common classes
- Fix ruamel.yaml type waivers that mypy sometimes ignores
- Drop some no longer valid TODO comments
- Replace '--t' by '-t' when creating a new plan with template
- Add a new cpu property `flag` to the hardware spec
- Fix duplicate export for Polarion hyperlinks
- Option to list locally cached images for testcloud
- Log out testcloud version in virtual provision
- Use yq instead of grep when testing YAML content
- Don't use specific addresses in virtual provision
- Polish workdir pruning - pathlib transition & logging
- Support for fuzzy matching subcommand
- Add new link relation `test-script` definition
- Remove `group` from the `multihost` specification
- Move "show exception" code to utils
- Add missing support for 0.0.55 and 0.0.48 API
- Add type annotations to tmt.steps.STEPS/ACTIONS
- Support logging "topics" to allow lower unnecessary verbosity
- Add support for right-padding of logging labels
- Move tools config to `pyproject.toml`, add Ruff
- Example to parametrize test selection via envars
- Merge run_command() and _run_command() into Command.run()
- Install beakerlib into images used in test/full
- Don't run `ShellCheck` on tests & decrease severity
- Support multiline strings for option help texts
- Fix tests run only in full testsuite

* Fri Apr 14 2023 Petr Šplíchal <psplicha@redhat.com> - 1.22.0-1
- Change help text of the `tmt --root` option
- Add support for `results.json` in custom results
- Proper support for the test `duration` format
- Prepend '/' to custom test result name if missing
- Document necessary packages for pip install on Ubuntu
- Tag cloud resources to `tmt` in Testing Farm
- Display guest multihost name even in dry run (#1982)
- Pass the `arch` option to the Beaker provider
- Use `job-id` instead of `guestname` in Beaker class
- Adjust the fix for the default branch handling
- Add support to get `ref` under the git worktree
- Fix dry mode handling when running a remote plan
- Enable the external `polarion` plugin tests
- Extract "run a command" functionality into a stand-alone helper
- Increase minimal severity of `ShellCheck` defects
- Display guest full name in `display` plugin report
- Push using `sudo rsync` when necessary
- Avoid warning from installing tmt as pre-commit
- Add test checking repeated test execution results
- Freeze the `yq` version to fix `el8` installation
- Update the `CODEOWNERS` file with more granularity
- Document current workaround for running scripts
- Install `beakerlib` before the `ShellCheck`
- Rename `Guest.full_name` to `Guest.multihost_name`
- Display guest full name in `html` plugin report
- Add test for template-based export plugin
- Add `kickstart` to the `artemis` provision plugin
- Extract just tar files in dist-git-source
- Add missing fields to custom results test
- Add shell linter `Differential ShellCheck`
- Always try to run dhclient in cloud-init in virtual provision
- Fix polarion report pruning and add or fix arguments
- Run `chcon` only if SELinux fs supported
- Require `beaker` provision in `tmt-all`
- Adjust the new `mrack` plugin spec, test and plan
- Add `beaker` provision plugin using `mrack`
- Adjust pip install to always upgrade to the latest
- Move `testcloud` url guessing logic out of `tmt`
- Hotfix Ubuntu with virtual provision
- Detect correct category when export to nitrate
- Add an entrypoint for interactive `tmt` sessions
- Fix internal handling of the `where` key
- Move logging labels to the beginning of lines
- Refactor CLI error reporting to improve readability
- Remove no longer needed cast around our custom Click context
- Display guest full name when showing its details
- Add `kickstart` section as a new specification key
- Add more controls for output colorization
- Rephrase `results.yaml` documentation and examples
- Fix `get_bootstrap_logger` name and docstring typo
- Expose guest info in results
- Enable `root` login and disable default `core` for rhcos
- Sanitize plan/test/story names before filtering
- Set default user `core` for rhcos in testcloud
- Remove no longer used "err" parameter of logging methods
- testcloud: Raise default limits
- Update log key content of results.yaml examples (#1834)
- Include guest name in execute phase data paths
- Adds "bootstrap logger" for logging before CLI options are recognized (#1839)
- Export `TMT_TEST_NAME` and `TMT_TEST_METADATA` (#1888)
- List supported operators in hardware requirement docs (#1867)
- Build tmt usable in inner guests for tests/full
- Target test-complement for tests/full
- Tag tests which are affected by how=full
- Use PROVISION_METHODS in tests
- Report individual test results in tests/full
- Use Require* classes for collection & installation of plugin requirements (#1766)
- Disable tracebacks if default branch is not found
- Assign a data path and serial number to each test in discover (#1876)
- Convert log path for results:custom
- Allow report result for itself in results:custom
- Support to import Makefile having '\\\n'
- Require `pylero` for the `polarion` subpackage
- Fix forgotten guest when Artemis provisioning times out
- Turn `tests.yaml` into a list of tests
- Simplify the `Result` class implementation
- Use `Path` instead of `os.path` in export code
- Use `Path` when working with logfile path
- Fix use of old `os.path.symlink()` in discover/shell
- Add /root/.local/bin to PATH on Centos Stream 8 in CI
- Install jq/yq for more readable tests in tmt test suite
- Fix Common class ignoring other branches of multiple inheritance tree
- Use Path instead of os.path in prepare/install plugin
- Convert path-like strings to `pathlib.Path` objects
- Change `Plugin.go()` to accept logger and extra environment
- Artemis API version may contain multiple integers
- Add logging `labels` used for prefixing messages
- Adds "full name" guest property for multihost logging

* Fri Feb 03 2023 Lukáš Zachar <lzachar@redhat.com> - 1.21.0-1
- Fix tmt-reboot without custom command
- Fix test /discover/libraries
- Add serialization callbacks to data class fields
- Use own private key for `provision.virtual`
- Adds a template-backed export plugin
- Polarion export fix component upload bug and upload id first
- Convert story ReST export to use a Jinja2 template
- Convert export-related code to plugins per format
- Do not clone the whole remote plan in dry mode
- Hardcode tmt git URL so test won't fail for PRs
- Add py.typed marker for 3rd party type annotations
- Fixes isort 5.10.1 installation issue
- Improve logging by `tmt.utils.wait()`
- Check packages are installed via debuginfo-install
- Always ignore failures for recommended packages
- Merge report plugins options into step data fields
- Dynamically find the current Fedora release
- Suggest using a pull request checklist template
- Include a simple Python code among the examples
- Apply normalization callback when updating data with CLI input
- Bump pre-commit linters - Flake8, Mypy, JSON schema, YAML lint & pygrep
- Use base implementation of provision plugin requirements
- Relay 'interactive' value for podman call
- Update Fedora versions in `upgrade` tests
- Apply `ShellScript` for the custom reboot command
- Update the `shell` discover specification
- Enable to sync git repo to SUT in `shell` discover
- Increase the default `utils.format()` indent a bit
- Define pull request Copr build job in Packit config
- Decouple logging from objects and base classes
- Enable `url` and `ref` as `shell` discover options
- Export `TMT_TREE` in other steps as well
- Add a new key `system` to the `hardware` spec
- Remove default for the dynamic `ref` evaluation
- Schema update and test for order in discover step
- Merge report plugins options into step data fields
- Add a test for hardware schema coverage
- Better type annotations of prepare/install scripts
- Move `jinja2` require to the main `tmt` package
- Define the new context dimension `initiator`
- Respect `TMT_WORKDIR_ROOT` variable in `testcloud`
- Annotate commands, command line elements and shell scripts
- Adjust the `reportportal` plugin implementation
- Implement the `reportportal` report plugin
- Require the latest `testcloud` package
- Define `srpm_build_deps` in the packit config
- Include the new web link in verbose `show` mode
- Add a clickable web link to test to polarion export
- Enhance `Links` to allow checking for any links at all
- Drop various guest `wake()` methods in favor of parent class
- Catch `SystemExit` during module discovery

* Thu Dec 08 2022 Lukáš Zachar <lzachar@redhat.com> - 1.20.0-1
- Do not prune `html` and `junit` reports
- Skip extending fmf context if cli context missing
- Connect needs is_ready property as well
- Cover setup.py with pre-commit Python checks
- Do not leak "private" fields into export
- Set guest hostname in testcloud provision
- Capture provision error when login is used
- Support `TMT_WORKDIR_ROOT` environment variable
- Support step data definitions carrying CLI options
- Adds flake8 coverage for bin/ directory
- Prune irrelevant files during the `finish` step
- Add junit plugin schema
- Support to import empty key from Makefile
- Deleting unsed and duplicite part of finish step
- Support absolute paths in HTML reports
- Capture exceptions when getting `image_url`
- Enable verbose output for `provision` & `prepare`
- Add support for Artemis v0.0.47 upcoming release
- Remove unused variables
- Initial support for passing ssh options from cli
- Update specification of the `where` multihost key
- Add a simple test demonstrating the upgrade testing
- Use custom subclass of click.Context for better annotations
- Extend the `duration` for tests using containers
- Change common class constructors to use keyword arguments only
- Make packit build with the next release.dev version
- Add basic test coverage for `tmt story export`
- Fix export of the story `priority` field
- Read source from correct directory if ref is used

* Wed Nov 09 2022 Lukáš Zachar <lzachar@redhat.com> - 1.19.0-1
- Protect args in rsync call
- Set tree root for the default plan tree as well
- Properly set the `tmt` script shebang on `rhel-8`
- Use image exists to check for container image
- Updates docs with example on `adjust` & `prepare+`
- Fix test duration enforcement
- Skip missing debuginfo packages in `recommend`
- Explicitly document extending the plan environment
- Fix ownership of a tmp directory propagated to container
- Support fetching remote repo for `shell` discover
- Fix default `framework`, remove old execution methods
- Add support for Artemis v0.0.46 upcoming release
- Handle an fmf fetch error in remote plan clone
- Do not truncate `RunError` output in verbose mode
- Warn user about data erasing after prepare step
- Formalize `data` package passed to the `Result` class
- Change order of plugin and guest classes in files
- Add `compatible` as a new hardware specification key
- Add `tpm` as a new hardware specification key
- Move the hardware specification into a separate page
- Improve fmf-id processing
- Add test for TTY state in test environment
- Login after each test using the `--test` parameter
- Mention version where important features were added
- Handle dist-git-sources for gitlab
- Fix getting CentOS via --how virtual
- Capture uncaught exceptions when using testcloud
- Update the overview of essential classes
- When following command line --how, do not iterate over step data
- Convert utils' Run unit tests to class-less tests
- Enable variable expansion for dynamic references
- Support beaker libraries as recommended packages
- Add `SpecBasedContainer.to_minimal_spec()` method (#1637)
- Enable context based plan parametrization
- Coverage for tests defined under `discover.shell`
- Fix `/tests/run/shell` access permission problem
- Add step data classes for provisioning and report
- Adjust support for the dynamic `ref` evaluation
- Add support for dynamic `ref` evaluation
- Add a test for fmf id parsing and normalization
- Fix NO_COLOR not being honored by executed command output
- Moves common command options into one place
- Log full chain of exceptions, not just the first cause
- Drop deprecated PluginIndex
- Add message to failure tags in junit report
- Update the pip installation plan
- Remove pointless reimport of tmt.base in discover steps
- Do not use f-string as a docstring
- Fix use of variable before assignment in `Plan.go`
- Fix variable redefinition in `discover/shell.py`
- Fix guest distro detection, do not throw results away
- Fix a typo in `cpu.sockets` hardware requirement
- Make links relative for report html
- Review all uses of `type: ignore` and link relevant issues
- Enhance ClickOptionDecorator type to announce identity
- Update `/tests/execute/upgrade/override` duration
- Review all uses of `Any` and link relevant issues
- Annotate all `cast()` calls with respective issues
- Move the `Result` class into a separate file
- Unblock mypy's follow-import setting
- Use set comprehension instead of list-in-set sequence
- Use `enumerate()` instead of `range(len())`
- Use dict comprehension instead of tuple-in-list-in-dict
- Replace two more list comprehensions with generators
- Replace GeneralError's "origin" with Python's "raise from"
- Fix normalization of the `Plan.context` key
- Adds a missing import to polarion plugin
- Update all linters to their most recent versions
- Define CPU HW components with more granularity
- Adjust the support for importing remote plans
- Add import plan feature and tests
- Add type annotations to `base.py`
- Fix test depending on ordering of elements in junit XML
- Adds type annotations to `tmt` itself
- Remove custom yet same implementation of step's show()
- Make sure `repo_copy` is gone before `make srpm`

* Mon Oct 10 2022 Petr Šplíchal <psplicha@redhat.com> - 1.18.0-1
- Fix recommended packages handling for rpm-ostree
- Add EFI configuration to the `tmt-reboot` script
- Fix adjust for precommit test
- Fix provision for coreos image
- Emit only non-default keys when constructing a test from `execute`
- Add flake8 config file for easier integration with IDEs
- Multiple scripts for CLI prepare -h shell
- Allow mypy to cover the whole tmt.plugins and tmt.steps
- Add typing for `steps/execute/upgrade.py`
- Fix name & default value of polarion's upload field
- Fixes enhancing of environment by local's guest implementation
- Ignore plan -n when searching for upgrade path
- Document & correct use of class conversion methods
- Print fmf tree location when schema unit test fails
- Custom results implementation
- Refactors internal link handling and storage
- Allow mypy to cover whole tmt.steps.prepare
- Add typing for `steps/execute/internal.py`
- Use workdir with safe names without special chars
- Adjust support for installing remote packages
- Support to install package from URL
- Make sure short option '-x' is covered
- Add Polarion as a source for test case import
- Print path to the used ssh identity
- Add typing for `steps/prepare/__init__.py`
- Use generator instead of list comprehension with any/all
- Fixes handling of default of --key in connect plugin
- Update test data for the debuginfo install test
- Add a helper for importing a member from a module
- Fix plan schema to allow custom context dimensions
- Allow mypy to cover whole tmt.steps.discover
- Remove support for the obsoleted `detach` executor
- Add typing for `steps/discover/fmf.py`
- Fix importing for pylero
- Allow mypy to cover whole tmt.steps.provision
- Replace blank "type: ignore" with more specific waivers
- Use the `SerializableContainer` for plugins' data
- Enhance SerializableContainer with default key value inspection
- Moves validation and normalization mixins to utils

* Mon Sep 05 2022 Lukáš Zachar <lzachar@redhat.com> - 1.17.0-1
- Unify Polarion case searching
- Error out if reboot timeout is exceeded
- Initialize workdir thread-safe
- Add support for remote playbooks in prepare
- Add plan schema for errata and minute plugins
- Correct rhts command names in stories file
- Print escaped command suitable for manual debugging
- Fix report plugin not getting arguments from fmf file
- Less eager to disable nitrate case during export
- Move `tag` and `tier` to common core attributes
- Use `/bin/bash` instead of `/bin/sh` for execute
- Reorder step and their base plugin classes
- Fix prepare/multihost docs to match implementation
- Teach schema validation tests to peek into other trees
- Clarify motivation for creating `id` during export
- Add link-polarion option and fix link searching bug
- Ignore race in last-run symlink creation
- Fix polarion tcmscaseid search
- Force order of clean operations
- Convert status/clean argument to option
- Report enabled plans/tests/stories via option
- Hint user if 'tmt init' creates nested root
- Require `libvirt-daemon-config-network` as well
- Add type annotation for /steps/prepare/install.py
- Encapsulate created file within script's dataclass
- Adds normalization layer to base classes based on fmf
- Fixes data class used for local guest creation
- Fixes Artemis guest data class link
- Making tests/full more usable
- Add typing for tmt/steps/provision/podman.py
- Add typing for tmt/steps/provision/testcloud.py
- Add typing for tmt/steps/provision/local.py
- Remove unused keys parameter from wake() methods
- Adds types describing tmt constructs when as stored in raw fmf data
- Typing /steps/provision/connect.py
- Allow raising an exception on validation errors
- Inject logger object to base node classes inheritance
- Fixes use of SSH keys in testcloud and connect plugins
- Annotate tmt.steps.provision
- Ask mypy to show error codes in its messages
- Testcloud expects disk and memory to be int
- Do not inherit classes from object
- Use keyword-only init in base fmf-backed classes
- Use decorator to register plugin methods
- Demonstrate inheritance on a virtual test example
- Add a simple hint how to write user messages
- Add typing for `steps/finish/ansible.py`
- Remove unneeded parameters for step load/save (#1428)
- Normalize step data to be always stored a list internally
- Display test/plan/story name in parametrized schema tests
- Allow numbers and booleans to be values of environment
- Give a reasonable error for old data format
- Add typing for tmt/steps/finish/__init__.py
- add typing for steps/discover/shell.py
- Adds a fmf node validation layer to core classes (Test/Plan/Story)
- Add missing keys `role` and `where` to schemas
- Extend plan schema with all known step plugin schemas
- Correcting rhts aliases & adding rhts opt.
- Adds a generic "wait for condition" primitive
- Disallow push/pull/execute if guest is unavailable
- Rename "default how" step attribute to enhance its visibility
- Use textwrap.dedent() to unindent docstrings

* Wed Aug 03 2022 Lukáš Zachar <lzachar@redhat.com> - 1.16.0-1
- Reboot has to check for boot time
- Fix path inside pre-commit test
- Cut circular dependency of libraries
- Update 'Develop' section of contribution docs
- Precommit hooks to call tmt * lint
- Schema loading helpers
- Package schemas in subdirectories too
- Implement reboot reconnect timeout configuration
- Add missing report specifications/docs
- Print result for execute -v
- Correct import assumption about script
- Ask mypy to check whole tmt.steps.report package
- Fixing the directory name escaping in 'cd' command
- Add polarion report plugin
- Add schemas for plans
- Write extra-nitrate as soon as possible
- Retry git clone without --depth=1 if it failed
- Support to lint attribute 'id'
- Do not apply test command filter in upgrade
- Fix export.py typing issues
- Refactor location and signature of Phase's go() method
- Simplify abort handling
- Backwards compatibility for rstrnt-abort
- Add type annotations for tmt/cli.py
- Add typing for tmt/export.py
- add typing for steps/discover/__init__.py
- Convert guest implementations to use serializable container for load/save
- Detect plugins by entry_point as well
- Add typing for `steps/execute/__init__.py`
- Add typing for `tmt/convert.py`
- Remove duplicated dist-git-source/dist-git-type
- Add typing for `steps/report/junit.py`
- Add typing for `steps/report/html.py`
- add typing for steps/report/display.py
- Add typing for steps/report/__init__.py
- tmt-file-submit is a bash script
- Add type annotations for tmt/options.py
- Backwards compatibility for `rstrnt-report-log`
- Support conditional requires with `pip` as well
- Remove duplicated short option in tmt lint
- Adjust the `rstrnt-report-result` implementation
- Backwards compatibility for `rstrnt-report-result`
- Set the `1777` permision for `/var/tmp/tmt`
- Adjust the fix for the `rpm-ostree` intallation
- Fix package installation using `rpm-ostree`
- Handle empty fmf file as an empty dictionary
- Fix distgit testsuite after tmt packaging change

* Sat Jul 02 2022 Lukáš Zachar <lzachar@redhat.com> - 1.15.0-1
- Require fresh testcloud with coreos support
- Bad substitution in tmt-reboot
- Ignore "certificate verify failed" error when handling retries
- Cache content of each loaded environment file
- Initial polarion support for test export
- Fixes names of Artemis API versions
- Convert FmfIdType from TypedDict to a dataclass
- Add CoreOS support to the testcloud provision
- Run containers with root user
- Retry getting environment file
- Test import --general is default now
- Add typing for steps/finish/shell.py
- Enhance tmt.utils.retry_session with timeout support
- Adjust the `rpm-ostree` install implementation
- Add support for the `rpm-ostree` package manager
- Add `environment-file` to possible Plan keys
- Avoid Library url conflict if repo doesn't exist
- Check changes are pushed before export nitrate
- Add typing for beakerlib.py
- Unbundle template from the report.html plugin
- Rename `uuid` to `identifier` to prevent conflicts
- Use `must` for all mandatory spec requirements
- Fail import for packages starting with minus sign
- Adds support for newer Artemis API versions
- Disable the extra verbose progress in testcloud
- Refactor internal executor scripts
- Adds "missing" imports to help IDEs follow objects
- Add typing for steps/__init__.py
- Implement the test `result` attribute
- Add typing for plugins/__init__.py
- Detect legacy relevancy during import as well
- Implement the new user story key `priority`
- Implement new class `SerializableContainer`
- Add schema for stories
- Add typing for steps/prepare/shell.py
- Add typing for steps/prepare/ansible.py
- Require fmf >= 1.1.0 (we need validation support)
- Package fmf root into the source tarball as well
- Add JSON Schema for tests
- Exclude namespaced backup in beakerlib
- Use --depth=1 when cloning git repos by default
- Handle missing nitrate user during export
- Removes unused GuestContainer.container_id attribute
- Every subpackage must require the main tmt package
- Introduce dataclasses as a requirement
- Avoid re-using image/instance for different values by testcloud plugin
- Add typing for multihost.py
- Except nitrate xmlrpc issues during import
- Exclude beakerlib's backup dir from guest.pull()
- Increase `duration` for the reboot-related tests
- Several release-related tests and docs adjustments

* Mon Jun 06 2022 Petr Šplíchal <psplicha@redhat.com> - 1.14.0-1
- Command 'tmt clean' should not run rsync at all
- Dist-git-source for Discover (fmf, shell)
- Adjust the new `id` key implementation
- Add a new core key `id` for unique identifiers
- Recommend qemu emulators for other architectures
- Copy the whole git repo only if necessary
- Reveal hidden errors during `testcloud` booting
- Use time for timeout handling in Guest.reconnect()
- Split `Guest` class to separate SSH-capable guests
- Explicitly set the docs language in the config
- Kill the running test when rebooting
- Extend the reboot timeout to allow system upgrades
- Allow selecting tasks directly from upgrade config
- Adjust the new `upgrade` execute plugin
- Allow specifying command for reboot
- Implement upgrade execute plugin
- Buildrequire python3-docutils, append plan adjust
- Implement `tmt tests export --nitrate --link-runs`
- Detect component from general plan during import
- Adjust the support for steps in standalone mode
- Add results method to ExecutePlugin
- Implement a common ancestor for Action and Plugin
- Allow abstractly excluding steps from runs
- Correctly handle tests --name '.' shortcut
- Rename WorkdirType to WorkdirArgumentType
- Fix workdir parameter type for tmt.utils.Common
- Allows importing jira issues as link-relates
- Enables mypy coverage for empty-ish Python files
- Adds type annotations to tmt.templates
- Prevent infinite recursion if --id is set
- Enable mypy check for Artemis provision plugin
- Adjust provision dry mode propagation, add a test
- Introduce new _options attribute to Common class
- Add specification for remote plans referencing
- Bootstrap type annotations
- Execute script should not be used with discover
- Add the `arch` key to the hardware specification
- Fix pip install instructions
- Disable network access when building in copr
- Ignore list for dist-git-source
- Remove the obsoleted `detach` execute method
- Fix login during `execute` and `prepare` step
- Import from Makefile with missing build target

* Mon May 02 2022 Petr Šplíchal <psplicha@redhat.com> - 1.13.0-1
- Add multiarch support to testcloud provision
- Consistent summary for test export --nitrate
- Allow dry mode for tests export --nitrate
- Add a nice provisioning progress to Artemis plugin
- Add support for the `where` keyword to `execute`
- Adjust support for export of multiple tests
- Add support for exporting multiple tests
- Basic multihost test for the httpd web server
- Update multihost specification with guest groups
- Add a provision plugin for Artemis
- Fix exclude option in fmf discover
- Reduce the number of execute calls for reboot
- Add support for reboot in interactive mode

* Mon Apr 04 2022 Petr Šplíchal <psplicha@redhat.com> - 1.12.0-1
- Add a command to setup shell completions
- Use /tmp instead of /run/user/ if not available
- Use separate examples in the test specification
- Add more story examples, simplify examples export
- Story.example can hold list of strings
- Fix traceback when connect plugin is used without hostname.
- Adjust disabled shell expansion in Common.run()
- Disable shell expansion in Common.run() by default
- Build `epel9` packages, update install docs
- Adjust the full test wrapper and document it
- Test which compiles tmt and runs its testsuite
- Add --exclude search option
- Correct regex for require read from metadata file
- Update document for creating virtual environment
- Option to export fmf-id from run discover -h fmf
- Allow import from restraint's metadata file (#1043)
- Do not disable building for power arch on Fedora
- Update documentation for plan parametrization
- Make .vscode ignored by git
- Drops basestring and unicode built-ins from utils
- Fix timeout behaviour in testcloud plugin
- Fixes possible test of None-ish CWD when running a command
- Remove workdir only when its defined
- Adjust the new `tmt plan export` feature
- New feature: tmt plan export

* Wed Mar 02 2022 Petr Šplíchal <psplicha@redhat.com> - 1.11.0-1
- Prevent koji build failures on unsupported arches
- Check remote git URL if it is accessible
- Implement a generic `requires` for all plugins
- Run commands in podman provision via bash
- Adjust implementation of the new `order` attribute
- Implement the Core attribute `order`
- Fix link generation in report.html
- Improve step name handling
- Enable shared volume mounts in podman provision
- Add support for multihost provision and prepare
- Adjust the dnf support for rsync install
- Add dnf support for rsync install
- Update links and refs after migration to `teemtee`
- Track output for reboot purposes on per-test basis
- Fix test --name '.' used with multiple plans
- Tweak test suite (duration, centos:8, datadir)
- Use `os.pathsep` to separate `TMT_PLUGINS` paths (#1049)
- Document framework:shell exit codes
- Add `html2text` to the `convert` pip dependencies

* Tue Feb 01 2022 Lukáš Zachar <lzachar@redhat.com> - 1.10.0-1
- Make reboot support a bit more backward compatible
- Ensure that workdir has a correct selinux context
- Use `centos:stream8` image instead of `centos:8`
- Disable X11 forwarding in ssh connections
- Fix traceback for login after last report
- Use `TMT_TEST_DATA` as location for `rlFileSubmit`
- Implement variables for storing logs and artifacts
- Adjust rsync installation on read-only distros
- Handle rsync installation on read-only distros
- Add hardware specification for hostname
- Correctly import multiple bugs from Makefile
- Remove dependency on the `python3-mock` package
- Adjust linting of manual test files
- Check Markdown files in tmt lint if `manual=True`
- Adjust pulling logs from the guest during finish
- Add guest.pull() to the finish step
- Update virtualization hints for session connection
- Improve error message for empty git repositories
- Minor modification of test result specification
- Use `where` instead of `on` in the multihost spec
- Clarify that `path` is defined from the tree root
- Adjust ansible requires for containers preparation
- Move the reboot scripts to a read/write directory
- Ignore read/only file systems reboot script errors
- Require either ansible or ansible-core
- Set the `TMT_TREE` variable during test execution
- Clarify that 'until' means until and including
- Update test debugging examples with --force option
- Add `bios.method` to hardware spec
- Improve environment variables specification a bit
- Adjust the ssh connection multiplexing
- Add support for ssh multiplexing

* Tue Nov 30 2021 Petr Šplíchal <psplicha@redhat.com> - 1.9.0-1
- Improve testcloud/virtual provider docs
- Disable UseDNS, GSSAPI for faster SSH in testcloud
- Use `extra-args` attr for ansible-playbook
- Fix el7 provision in testcloud user session
- Adjust the instructions for migrating from STI
- Document how to migrate tests from STI to tmt
- Allow to pick objects by --link
- Generate ecdsa key in testcloud
- Simplify plugin keys handling in wake() and show()
- Add support for Beakerlib's rlFileSubmit
- Revert requiring exact beakerlib version
- Dist git source can contain multiple files
- Symlink worktree for discovered shell tests
- Read environment variables from options only once
- Correctly handle empty environment files
- Use distro values from context for dist-git type
- Make tests --name to just prune discovered tests
- Enable duplicate test names and preserve ordering
- Require beakerlib-1.28 for beakerlib tests
- Adjust the dist git source discover implementation
- Discover tmt tests from sources
- Reenable plans/install/docs
- Correct the `playbook` attribute in the spec (#948)
- Ansible plugin for Finish step
- Thread processing of executed commands inside tmt
- Adjust `tmt test lint` test for old yaml format
- Canonical name for centos-stream in dimension
- Remove obsoleted conditionals from the spec file
- Use a fresh sphinx when building the readthedocs
- Allow to specify session type (system/session)
- Package tmt.plugins to store arbitrary plugins
- Ignore ssh connection closed during reboot
- Improve error message for the missing step name
- Document how to integrate tests with other tools
- Use the recommended format of the copyright notice
- Update notes about the release process
- Update the hardware specification with new keys

* Thu Sep 30 2021 Lukáš Zachar <lzachar@redhat.com> - 1.8.0-1
- Add support for reboot in a reused provision
- Solve the reboot race condition
- Adjust the current git remote improvement
- Use current git remote for url in fmf-id
- Implement option to exit after first failure
- Clarify and update spec for the discover step
- Adjust the multihost test specification
- Add the multihost testing specification
- Make run --force behave more expectably
- Increase duration for tests using containers
- Rename soon-to-be deprecated resultcallback
- Remove the minute.obsolete provision plugin
- Document how to create a new minor/major release
- Explicitly mention '.' as special value for names
- Add Github Action for PyPI releases
- Improve fetching remote environment files
- Adjust the check for rsync before pull and push
- Install `rsync` before guest.pull()
- Second chapter of the Guide: Under The Hood
- Simplify the search for step method options
- Produce better errors for unsupported plugins
- Add more ignored files, categorize gitignore more
- Extend .gitignore with a few more common patterns
- Export fields of a case should be checked by lint
- Adjust the bugzilla support in test export
- Test export can link case to bugzilla
- Document the support for `open` key in html report
- Allow html report to be opened by plan
- Require essential packages for tmt testing
- Skip the docs test until the Sphinx issue is fixed

* Wed Aug 18 2021 Petr Šplíchal <psplicha@redhat.com> - 1.7.0-1
- Adjust support for exporting test fmf identifiers
- Add --fmf-id option for tests export
- Fix regression in image listing
- Update hardware spec with units and current status
- Adjust the reboot support in the internal executor
- Add support for reboot to internal executor
- Always try to save guest details
- Give hints about available report methods
- Handle libvirt exceptions correctly
- Handle FileNotFoundError when running commands
- Adjust framework detection during test import
- Detect test framework during test import
- Adjust the reboot command test, minor enhancements
- Adjust reboot command implementation
- Implement the reboot class and subcommand
- Adjust the improved login step selection
- Login after last done step without --step option
- Adjust default shell options implementation a bit
- Make multiline shell scripts fail on error
- Ensure environment files are within metadata tree
- Add pycharm .idea to .gitignore
- Ensure environment-file paths are only relative
- Adjust the 'environment-file' implementation
- Implement the 'environment-file' option
- Mention required packages on the Contribute page
- Migrate to ruamel.yaml
- Adjust tmt lint implementation
- Add tmt lint command
- Do not expand the process environment variables
- Adjust legacy match to cover both rhel and centos
- Guess pci/net when libguestfs python is missing
- Add timestamp to the tmt debug output
- Restart sshd on EL8 to prevent delays after boot
- Support systemd-networkd systems without nm too
- Testcloud: Use cache='unsafe' for a nice IO boost
- Check invalid attributes in plans with lint
- Require correct testcloud version in setup.py
- Adjust the support for plan parametrization
- Implement plan parametrization from environment
- Deprecation timing, mention vagrant box support
- Fix exit code for tmt story lint
- Require testcloud with the url guessing support
- Use testcloud for image url guessing
- Update the RHEL 8 / CentOS 8 install instructions
- Accept more ssh keys in the API
- Require a full path for local images in testcloud
- Adjust the conversion of Makefile types to tags
- Convert Type from Beaker Makefile into tags
- Make sure pip is available for integration testing
- Disable the white space test for container/virtual
- Use IdentitiesOnly=yes when key or password is set

* Wed Jun 02 2021 Petr Šplíchal <psplicha@redhat.com> - 1.6.0-1
- Adjust the new plugin documentation
- Add plugin examples and documentation
- Ensure that the discover git reference is a string
- Report plugin for JUnit output
- Fix issue when raising error for NoneType
- Print better error when nitrate testcase not found.
- Use `count=True` for multiple flag options
- Add option to explicitly use default plan
- Adjust debuginfo installation, add test coverage
- Use debuginfo-install for installing debuginfos
- Update the documentation based on refactoring
- Implement tmt story lint
- Refactor Node class to Core
- Correctly handle spaces in file/directory names
- Hand over plan environment during local execution
- Do not execute manual test cases
- Fix option handling for plugins with common prefix
- Propagate options to guests based on the step
- Support fetching libraries from a local directory
- Add a simple example of a test written in ansible
- Pass environment variables to ansible (local)
- Pass environment variables to ansible (virtual)
- Adjust warning for extra lines in Makefile targets
- Add test import warning for run and build targets
- Enable a few more pre-commit hooks, sort imports
- Give a warning about the obsoleted minute plugin
- Clarify adjust dependency on explicit context
- Fix the EPEL installation instructions
- Adjust the new list options for the minute plugin
- New print method, used now in minute plugin
- Implement listing available minute images/flavors
- Update default option values for verbose and debug
- Avoid creating workdir on --help
- Do not keep run workdir during testing
- Clean up the code style, remove the vagrant plugin

* Fri Apr 30 2021 Petr Šplíchal <psplicha@redhat.com> - 1.5.0-1
- Enable and document `pre-commit` and `autopep8`
- Reorganize feature stories, fix title duplication
- Prepare/install story for package development.
- Add package preparation scenarios from Fedora CI
- Prepare/install story for released packages
- Add new stories related to package preparation
- Fix login not working for cloud images
- Work around a seccomp podman issue on centos-8
- Tag multihost tests during import from Makefile
- Adjust the simple test for ansible prepare
- Remove hardcoded ansible_python_interpreter=auto
- Fix lint and use it on the tmt repo itself
- Obsolete the minute provision plugin
- Update the documentation for contributors
- Do not assert installed packages for recommend
- Show link to the full debug log in the html report
- Implement tmt clean command
- Require a newer fmf which supports storing data
- Allow to specify port in provision.connect
- Surround classes and functions with 2 blank lines
- Fix order of imports, sort them alphabetically
- Update the provision step hardware specification
- Fix tmt plan lint for multiple configurations
- Add tmt status examples section
- Add a context adjust example for the prepare step
- Adjust the git suffix stripping for known forges
- Strip git suffix from pagure/gitlab/github repos
- Enable install plans for pull request testing
- Adjust the essential attributes description
- Document the essential class attributes
- Improve the prepare step documentation
- Correctly convert relevancy with the `!=` operator
- Print note in report.html if it exists
- Add note about error for beakerlib results
- Adjust progress bar for the internal executor
- Add test progress bar to non-verbose mode
- Adjust the attribute linting for tests
- Lint attribute names for test
- Human friendly names for VMs

* Tue Apr 06 2021 Petr Šplíchal <psplicha@redhat.com> - 1.4.0-1
- Create a copy of nitrate testplans for iteration
- Check the rsync as the first preparation step
- Use an empty worktree if no metadata tree found
- Adjust manual test instructions export to nitrate
- Export manual test case fields to nitrate
- Adjust the worktree implementation and test
- Implement shared worktree for the tests
- Adjust the improved verdict implementation
- Correct the verdict function, align docstring
- Print final image name in minute plugin
- Adjust the improved plan linting a bit
- Improve plan linting
- Implement port in Guest, show in verbose mode
- Use qemu user mode in the testcloud provision
- Support excluding packages during installation
- Support enabling/disabling plans and stories
- Do not link and remove general plans by default
- Improve general plans handling during test export
- Match by name prefix in discover.modified-only
- Passthrough non-zero exits for beakerlib execution
- Adjust the dry mode implementation for tmt init
- Implement dry mode for the tmt init command
- Do not use the spec release for the pip version
- Simplify story, plan and test search methods
- Do not use mutable objects as default arguments
- Prevent duplicate content in generated docs
- Ignore the nitrate migration warning during import
- Better summary for new exported tests
- Adjust exception handling in the testcloud plugin
- Make the testcloud ProvisionError more verbose
- Use IPv6 enabled 1MT network by default
- Improve debugging of tests using click runner
- Fix step selection for --before and --after
- Adjust the prepare test and pull/push enhancements
- Add prepare/shell test and pull/push enhancements
- Test filter on command line overrides config
- Improve handling of verbose and debug options
- Verify automated test case import from nitrate
- Enable copr repo even if no package is provided
- Improve documentation of tests, plans and stories
- Use fmf to store the newly created nitrate case id
- Adjust the hint about increasing the test duration
- Add hint to stdout in case of timeout
- Catch all exceptions when evaluating --condition
- Fix missing overview on the readthedocs.org site
- Adjust style of the new nitrate integration test
- Nitrate integration testsuite with requre
- Always enable force mode for display/html report
- Improve documentation, clearly show draft stories
- Test filter on command line overrides config
- Print unofficial attributes in tmt tests show -vv
- Adjust dry mode fix for test/plan/story create
- Implement dry mode for tmt test/plan/story create
- Support NO_COLOR to disable colored output
- Add test duration to `results.yaml`
- Adjust checking for duplicates during test export
- Prevent creating duplicate test cases in Nitrate
- Use singular for 'gate' as defined in the spec
- Fix gates conversion & drop artifacts
- Adjust a bit the shell completion instructions
- Describe how to enable shell completions
- Extend the duration test to cover positive results
- Detect timeout for Beakerlib, use TESTRESULT_STATE
- Improve tmt test path linting
- Clarify playbook path for ansible prepare plugin
- Adjust warning about the invalid disabled step
- Only warn on invalid disabled step
- Use date-service to get correct instantiation time
- Prevent keys mutation when searching plans/stories
- Cache fmf_id property
- Store relevant bugs during test import
- Avoid mutating `keys` default in .tests()
- Use the new execute method syntax for tmt tests
- Clean up obsolete test metadata

* Thu Feb 25 2021 Petr Šplíchal <psplicha@redhat.com> - 1.3.1-1
- Add test for prepare freeze
- Make file descriptors non-blocking
- Update the specification and stories to use link
- Implement the new core attribute 'link'

* Tue Feb 23 2021 Petr Šplíchal <psplicha@redhat.com> - 1.3.0-1
- Set timeout on select calls in utils._run()
- Show the current tmt version in the debug log
- Revert support for the 'el' distro shortcut
- Strip whitespace before relevancy comment
- Ensure rsync is installed on the guest if needed
- Use the default branch in the discover fmf plugin
- Suport the 'el' shortcut for the distro context
- Implement the 'tmt --version' option [fix #445]
- Adjust test create test, fix missing dots
- Support creating tests in the current directory
- Rename container images, update install docs
- Fixup Dockerfiles to build in quay.io.
- Support building mini and full tmt container image
- Add a Dockerfile for container with tmt
- Fix dependency error messages
- Use a better trigger name for source code changes
- Add a new 'Check Report' section to examples
- Add the --force explanation in the documentation
- Extend the test coverage to check for active runs
- Add basic test coverage for tmt status
- Restore context after processing each run
- Correctly handle an undefined step status
- Load default plan when no root is present
- Implement tmt status command
- Define command-line interface for status command
- Print library in error message during ref conflict
- Adjust the default branch handling for libraries
- Handle default branch in Library
- Adjust test duration, clean up old test metadata
- Improve timeout handling (fix an infinite loop)
- Adjust default timeout in the testcloud provision
- Remove obsolete unit test coverage for steps
- Adjust the filtering support, fix docs building
- Allow filtering using custom L1 metadata
- Allow filtering with lowercase bool names
- Handle exceptions when applying filters and conditions
- Share code for filters & conditions, test coverage
- Apply filters after applying defaults and conversions
- Fix IPv4 parsing when booting minute machine
- Remove all hacks for the old cruncher executor
- Remove the whole rhts-lint line during test import
- Remove the old convert test from unit tests
- Adjust contact handling to work with manual tests
- Fix contacts without name during tmt test import
- Finalize the specification of the 'link' attribute
- Add specification of the new core attribute 'link'
- Enough of dreaming, let's go to the forest! :)
- Update the overview of core classes, minor cleanup
- Add missing required packages for pip install
- Implement tmt run --follow option for checking log
- Extra check for required packages when using yum
- Clean up obsolete names in examples and templates
- Update the test checking for relevancy conversion
- Adjust storing test case id for new nitrate cases
- Append nitrate id when exporting instead of rewrite
- Skip prereserve check if custom flavor requested
- Use special compare operators only if minor given
- Adjust support for selecting modified tests
- Allow selecting only tests that have changed in git
- Remove the duplicate build job from packit config
- Verify the old beakerlib functions using Makefile
- Enable debug output using the TMT_DEBUG variable

* Fri Dec 11 2020 Petr Šplíchal <psplicha@redhat.com> - 1.2.1-1
- Manual state for manual nitrate tests
- Define framework for all beakerlib libraries tests
- Remove the remaining test case relevancy leftovers

* Wed Dec 09 2020 Petr Šplíchal <psplicha@redhat.com> - 1.2-1
- Minor adjustment of the beakerlib test template
- Adjust the new test checking the error output
- Print errors to stderr
- Fix check for selecting plans during tmt run
- Update test coverage, fix finish step example
- Update spec/stories implementation coverage
- Skip import of manual cases with script
- Import header and footer from Nitrate
- Implement conversion between relevancy and adjust
- Support short options for selecting tests & plans
- Document the display and html report in the spec
- Explain the difference between fmf and tmt
- Fix the last missing framework in library tests
- Adjust the docs update and title implementation
- Implement a new story attribute 'title' (L3)
- Small documentation cleanup
- Simplify plan setup, move old plans to examples
- Store the whole debug log in the top run directory
- Add test for pip installability
- Add a new plan to cover minimal installation
- Move html report plugin into a separate subpackage
- Use 'output.txt' filename for the main test output
- Update required fmf version in setup.py
- Improve the css style for the html report
- Fix blocking read in Common.run
- Adjust a bit the improved html report
- Improve report-html --open
- Implement adjusting metadata based on the context
- Adjust the new 'html' report method
- New report --how html available
- Adjust environment import from Makefile metadata
- Import environment from Makefile metadata
- Update old beakerlib paths during tmt test import
- Adjust a little bit the user story templates
- Support libraries stored deep in the repositories
- Enable the new coverage stories section in docs
- First stories to cover tests coverage mapping
- Recommend using login shell in libvirt hints
- Use nitrate naming for the manual field export
- Export manual attribute to nitrate
- Store complete initialized data in metadata.yaml
- Merge the improved minute error messages [#425]
- Adjust a bit the minute provision error messages
- Handle testcloud problem with the images directory
- Handle tracebacks in minute provision
- Multiple enhancements for package preparation
- Gracefully handle invalid library reference

* Thu Oct 22 2020 Petr Šplíchal <psplicha@redhat.com> - 1.1-1
- Convert adds extra-summary as well
- Simplify test directory copy with enabled symlinks
- Select latest minute image only from released images
- Allow specifying exact RHEL version using a short name
- Preserve symlinks during discover, pull and push
- Always run Login plugin even if step is done
- Suggest some useful aliases for common use cases
- Correct type of Tier attribute in examples
- Define basic hardware environment specification
- Import manual data for automated tests
- Tag tests which can be run under container/virtual
- Give hints to install provision plugins [fix #405]
- Handle nicely missing library metadata [fix #397]
- Update the test data directory name in the spec
- Extend duration for tests using virtualization
- Use a better name for the test data path method
- Provide aggregated test metadata for execution
- Send warnings to stderr, introduce a fail() method

* Wed Oct 07 2020 Petr Šplíchal <psplicha@redhat.com> - 1.0-1
- Correctly handle framework for new plans and tests
- Move runtest.sh adjustments into a single function
- Add the executable permission to runtest.sh
- Less strict removing sourcing of rhts-environment
- Use metadata directory as the default for path
- Implement the new L1 attribute 'framework'
- Explicitly enable copr_build for pull requests
- Handle missing library in existing repository
- Update the overall tmt description and examples
- Enable builds from master in the main copr repo
- Merge packit config for copr builds from master
- Use packit repository for copr builds from master
- Gracefully handle invalid test output
- Build in COPR for master via packit
- Add hint about caching the dnf package metadata
- Add two hints about easy login for experimenting
- Merge debug messages for the minute plugin [#361]
- Adjust the minute provision debug messages wording
- Use the internal tmt executor by default
- Add more debug messages to minute provision
- Remove the remaining 'tmt test convert' references
- Prevent shebang mangling for detached executor
- Merge the minute and install plugin docs [#345]
- Adjust the minute and install plugin documentation
- Merge the manual test import documentation [#347]
- Adjust the manual test documentation wording
- Merge rhts-environment source line removal [#344]
- Adjust rhts-environment source line removal
- Add missing extra-* keys to the test import
- Add docs for manual case import
- Disable authentication when fetching libraries
- Document the install prepare method
- Document the minute provision method
- Remove sourcing of rhts-environment in runtest.sh
- Add minute to supported provision methods of prepare

* Mon Sep 07 2020 Petr Šplíchal <psplicha@redhat.com> - 0.21-1
- Adjust manual test case import from nitrate [#319]
- Move the test convert deps into a separate package
- Support importing manual test cases from Nitrate
- Merge the non-zero exit codes for linting errors
- Fix several test export issues [fix #337]
- Adjust distro checks, remove the dry parameter
- Generalized Guest.details() [fix #310]
- Adjust the test coverage for tmt plan/test lint
- Update documentation with virtualization tips
- Make sure the duration timer is always canceled
- Merge the new retry_session functionality [#328]
- Exit with non-zero code if linting fails
- Merge fix for the double fmf extension [#327]
- Prevent koji from trying to build packages on i686
- Retry requests in case of network failure
- Avoid double fmf extension when creating plans and stories
- Improve the maximum test duration handling
- Remove vagrant from tmt-all recommended packages
- Detect beakerlib libraries from recommend as well
- Simplify packit custom create archive command
- Make the httpd test example a bit more interesting
- Append dots to fix tmt run --help message summary
- Document multiple configs and extending steps

* Tue Jul 28 2020 Petr Šplíchal <psplicha@redhat.com> - 0.20-1
- Move libraries handling into a separate module
- Adjust loading variables from YAML files [#316]
- Support environment variables from YAML files
- Give a nice error for expired kerberos [fix #57]
- Merge Guest relocation and documentation [#307]
- Describe essential Guest methods in more detail
- Update test import story and documentation
- Merge extra-task as summary in test export [#304]
- Move default plan handling into a single method
- Move the Guest class from base to steps.provision
- Save root in run.yaml
- Document L1 metadata defined in the discover step
- Improve Makefile editing during test import
- Use extra-task as summary in test export
- Mention default methods in the step help message
- Handle invalid url when library provided as fmf id
- Allow library git clone to fail

* Fri Jun 12 2020 Petr Šplíchal <psplicha@redhat.com> - 0.19-1
- Make the discover step a little bit more secure
- Improve basic and verbose output of tmt plan show
- Improve default plan handling and more [fix #287]
- Adjust the compose check retry in testcloud
- Retry Fedora compose check in testcloud [fix #275]
- Update development section and library example
- Support fetching beakerlib libraries in discover
- Add nitrate to the setup.py extra requires
- Add a workflow-tomorrow integration test example
- Add 'duration' into the test results specification

* Mon Jun 01 2020 Petr Šplíchal <psplicha@redhat.com> - 0.18-1
- Add virtual plans for supported provision methods
- Implement description in 'tmt plan show' as well
- Implement tmt run --remove to remove workdir
- Extend the login/step test to cover failed command
- Do not fail upon command fail in interactive mode
- Implement the internal tmt execute step method
- Move all prepare/install tests to tier level 3
- Merge the new manual test specification [#247]
- Merge the new L1 attribute 'recommend' [#265]
- Adjust the manual test specification and examples
- Implement 'recommend' for installing soft requires
- State explicitly that execution is finished
- Simplify beakerlib template, add test for init
- Manual test case specification and examples
- Implement exit codes, handle no tests [fix #246]
- Merge the interactive shell login command [#258]
- Adjust support for shortened 1MT image names
- New login command to provide a shell on guest
- Add support for shortened 1MT image names
- Add support for running tests without defined plan
- Ignore save() in the execute step unit test
- Update the default run example with fresh output
- Show kernel version only in verbose mode

* Sat May 23 2020 Petr Šplíchal <psplicha@redhat.com> - 0.17-1
- Use emulator_path instead of hard-coded qemu path
- Improve a bit the --force option description
- Use consistent naming for provision subpackages
- Add 'mock' to extra requires (needed to make docs)
- Move podman and testcloud plugins into subpackages
- Enable epel for packit build & testing farm
- Move vagrant from requires to recommends (tmt-all)

* Mon May 18 2020 Petr Šplíchal <psplicha@redhat.com> - 0.16-1
- Merge the fix and test for run --force [#245]
- Merge the improved display report [#241]
- Adjust the display report plugin verbose output
- Adjust general plan linking and component check
- Clean up the run workdir if --force provided
- More verbose modes for report --how display
- Link plans, handle missing components in export
- Import and listify of contact
- Disable Tier 3 tests by default (need bare metal)
- Move Tier 0 tests into a separate directory
- Merge the new 1minutetip provision plugin [#225]
- Adjust the 1minutetip provision plugin
- Add support for tmt run --after and --before (#237)
- Support string in test component, require and tag (#233)
- Add support for installing local rpm packages
- Add 1minutetip provision plugin
- Implement tmt run --since, --until and --skip (#236)
- Merge pull request #234 from psss/testcloud-aliases
- Update the last run id at the very end of run
- Support short Fedora compose aliases in testcloud
- Convert the finish step into dynamic plugins
- Convert the report step into dynamic plugins
- Convert the execute step into dynamic plugins
- Escape package names during installation
- Deduplicate inherited keys in test import [fix #8]

* Wed Apr 29 2020 Petr Šplíchal <psplicha@redhat.com> - 0.15-1
- Implement executing the last run using --last
- Adjust support for modifying plan templates
- Add a way how to edit values in a new template
- Explicitly mention supported distros in the docs
- Convert provision/prepare into dynamic plugins
- Describe difference between --verbose and --debug
- Support fmf name references in docs, update spec
- Support multiple verbose/debug levels [fix #191]
- Remove forgotten 'Core' section from stories
- Implement Plugin.show() for a full dynamic support
- Improve the workdir handling in the Common class

* Thu Apr 16 2020 Petr Šplíchal <psplicha@redhat.com> - 0.14-1
- Workaround yaml key sorting on rhel-8 [fix #207]
- Fix test discovery from the execute step scripts
- Merge discover step documentation and fixes [#204]
- Document the discover step, fix issues, add tests
- Simplify the minimal example, adjust tests
- Move fmf_id() to Node class, minor adjustments
- Allow to print fmf identifier in tmt tests show
- Merge manual tests story and examples [#198]
- Add a story and examples describing manual tests
- Sync more extra-* attributes when exporting [#199]
- Enable checks for essential test attributes
- Handle require in Dicovery
- Store imported metadata in a sane order [fix #86]
- Enable Python 3.8 in Travis, update classifiers
- Add missing 'require' attribute to the Test class
- Fix long environment for run.sh [fix #126]
- Merge dynamic plugins and wake up support [#186]
- Implement dynamic plugins and options [fix #135]
- Suggest using 'tmt init' when metadata not found
- Merge improved import of tier from tags [#187]
- Adjust tier import from test case tags
- Merge tmt test export --nitrate --create [#185]
- Adjust suppport for creating new nitrate testcases
- Allow creation of nitrate cases when exporting
- Create tier attribute from multiple Tier tags
- Fix run.sh to work with RHEL/CentOS 7 as well
- Implement wake up for Run, Step and Discover

* Wed Apr 01 2020 Petr Šplíchal <psplicha@redhat.com> - 0.13-1
- Merge the improved test import checks [#179]
- Adjust checks for missing metadata
- Add checks for missing metadata.
- Implement public_git_url() for git url conversion
- Define required attributes and duration default

* Wed Mar 25 2020 Petr Šplíchal <psplicha@redhat.com> - 0.12-1
- Import the testcloud module when needed [fix #175]
- Update implementation coverage of stories & spec
- Discover only enabled tests [fix #170]
- Correctly handle missing nitrate module or config
- Use raw string for regular expression search

* Mon Mar 23 2020 Petr Šplíchal <psplicha@redhat.com> - 0.11-1
- Merge default images for podman/testcloud [#169]
- Do not export empty environment to run.sh
- Merge vagrant check for running connection [#156]
- Adjust vagrant check for running connection
- Merge test export into nitrate [#118]
- Adjust 'tmt test export --nitrate' implementation
- Use fedora as a default image for podman/testcloud
- Move testcloud back to the extra requires
- Always copy directory tree to the workdir
- Add an example with test and plan in a single file
- Do not run tests with an empty environment
- Check for non-zero status upon yaml syntax errors
- Export test cases to nitrate
- Merge test import using testinfo.desc [#160]
- Adjust test import using testinfo.desc
- Use testinfo.desc as source of metadata
- Add environment support to the discover step (#145)
- Add a new story describing user and system config (#143)
- Check if connection is running in Vagrant Provision

* Wed Mar 11 2020 Petr Šplíchal <psplicha@redhat.com> - 0.10-1
- Merge fixed environment support in run.sh [#99]
- Add container and testcloud to tmt-all requires (#157)
- Rename dict_to_shell() to better match content
- Make path mandatory in run.sh.
- Handle execution better in run.sh
- Implement --env for testcloud provisioner
- Merge run --environment support for podman [#132]
- Fix container destroy, plus some minor adjustments
- Use cache 'unsafe' for testcloud (#150)
- Add --env option and support in podman provisioner
- Warn about missing metadata tree before importing
- Move testcloud to base requires, update README (#153)
- Destroy container in finish only if there is any
- Merge tmt test import --nitrate --disabled [#146]
- Adjust the disabled test import implementation
- Add an overview of classes (where are we heading)
- Import non-disabled tests
- Add a 'Provision Options' section, update coverage
- Support selecting objects under the current folder
- Add a link to details about fmf inheritance
- Move requirements under the Install section
- Mock testcloud modules to successfully build docs
- Include examples of plan inheritance [fix #127]
- Update implementation coverage for cli stories
- Add testcloud provisioner (#134)
- Merge the new story for 'tmt run --latest' [#136]
- Move run --latest story under run, fix code block
- Fix invalid variable name in the convert example
- Use 'skip' instead of 'without', simplify default
- Add rerun cli shortcut
- Make sure we run finish always
- Update the docs making '--name=' necessary (#138)
- Clarify environment priority, fix release typo
- Add environment specification
- Remove copr build job from packit (not necessary)
- Use the 'extra-summary' in the output as well
- Use 'nitrate' consistently for tcms-related stuff
- Prefix all non-specification keys [fix #120]
- Show a nice error for an invalid yaml [fix #121]
- Move container plan to common provision examples
- Remove tmt-all dependency on vagrant-libvirt
- Do not use red for import info messages [fix #125]
- Show a nice error for weird Makefiles [fix #108]

* Mon Feb 24 2020 Petr Šplíchal <psplicha@redhat.com> - 0.9-1
- Rename the 'test convert' command to 'test import'
- Include 'path' when importing virtual test cases
- Extract test script from Makefile during convert
- Do not import 'fmf-export' tag from nitrate [#119]
- Merge the improved component import [#115]
- Several adjustments to the component import
- Merge the improved requires parsing [#113]
- Fix parsing multiple requires from Makefile
- Fail nicely if executed without provision (#112)
- Make sure the copr command is available in dnf
- Fix handling defaults for options, adjust wording
- Read 'components' from nitrate when converting
- Read requires as list when converting tests
- Make it possible to pass script on cmdline
- Mention libvirt and rsync in Fedora 30 workaround
- Move podman image check and pull under go()
- Simple destroy implementation for podman provision
- Add Fedora 30 installation instructions [fix #105]
- Merge podman support for the provision step [#106]
- Several adjustments to the podman implementation
- Fix _prepare_shell in podman provisioner
- Add podman provisioner
- Update the test case relevancy specification (#102)
- Move copy_from_guest to provision/base.py (#75)
- Several minor adjustments to the restraint story
- Add user story for restraint
- Merge different summaries for subpackages [#97]
- Remove macro from the tmt-all subpackage summary
- Add different summaries for sub-packages
- Mention 'fmf-export' tag in the test export story
- Merge optional PURPOSE in test convert [#89]
- Handle missing duration or nitrate case in convert
- Add support for wrap='auto' in utils.format()
- Use local fmf repository for the basic plan (#94)
- Merge test import documentation updates [#90]
- Merge tag, status, pepa & hardware for test import
- Several test import adjustments related to #91
- Fix deduplication bug when converting tests
- Read more attributes from nitrate when converting
- Update examples doc for converting tests
- Update execute step examples for shell
- Simplify packit configuration using 'fedora-all' (#88)
- Optional attributes when converting.
- Update execute and report step specification
- Add spec for results.yaml and report.yaml (#66)
- Add a story for exporting tests into nitrate (#83)
- Add the 'require' attribute into the L1 Metadata
- Update the Metadata Specification link in README
- Improve 'tmt test convert' command implementation

* Wed Jan 15 2020 Petr Šplíchal <psplicha@redhat.com> - 0.8-1
- Do not create bash completion script during build
- Require the same version, fix changelog entry
- Create fmf for each tcms case when converting. (#78)

* Tue Jan 14 2020 Petr Šplíchal <psplicha@redhat.com> - 0.7-1
- Make the package build for epel7 and epel8
- Implement test discover from execute shell script
- Disable /plan/helps for running in cruncher (#74)
- Do not fail ansible execution on 'stty cols' error
- Use a list for storing converted requires
- Add Requires to main.fmf when converting tests (#65)
- Fix command debug output to join tuples as well. (#77)
- Set 80 chars for ansible-playbook on localhost
- Use tmt to init tree, extra folder for playbooks
- Fix log and error handling in execute
- Fail in run.sh if there are Missing tests.
- Use sudo in prepare step to allow local execution
- Fix run_vagrant() to work with shell=True
- Use tmt init --template, not --mini|--base|--full (#69)
- Add a simple local provision plan to examples
- Simplify step selection test, simple local example
- Fix conflicting options, revert copr config
- Add `--guest` support for the provision step
- Depend on git-core and not the full git package (#64)
- Use shell=True as a default in utils' run()
- Put quotes in `pip install .[*]` in README (#67)
- Use parent run context to check for enabled steps
- Improve the enabled steps implementation
- Add 'mock' to the extra test requires [fix #63]
- Add a new story for developing upgrade tests
- Update fedora targets for packit
- Add vagrant to BuildRequires (needed to run tests)
- Add stories for connecting to a provisioned box
- Separate the provision step into multiple stories
- Fix provision tests to work with older mock (#51)
- Install the latest mock module for testing
- Default to vagrant provision, use the tree root
- Update documentation coverage links
- Move new docs to examples, adjust style & content
- Add prepare functionality to local provision
- Import examples from @psss's talk
- Add an argument to ProvisionBase.copy_from_guest (#41)
- Remove unused imports, fix crash, shell prepare
- Initial prepare and finish steps implementation
- Document the vagrant-rsync-back plugin workaround
- Fix beakerlib execution, show overall results
- Better execute with logs and better run.sh
- Implement 'tmt init --base' with working examples
- Add git to the main package requires
- Add tmt & python3-nitrate to the tmt-all requires
- Create subpackage 'tmt-all' with all dependencies
- Use package_data to package the test runner
- Apply requested file mode in create_file()
- Run tmt tests local by default, fix provision show
- Implement image selection using provision --image
- Do not re-raise tmt exceptions in debug mode
- Package the runner, dry mode in Common.run()
- Support multiline output in common display methods
- Enable command line filtering in discover.shell
- Default discover method has to be 'shell'
- Fix Common.run() to capture all output, log all
- Fix broken test/plan/story create, add some tests
- Better config handling in ProvisionVagrant.
- Implement 'sync-back' and simple VagrantProvision.

* Mon Nov 04 2019 Petr Šplíchal <psplicha@redhat.com> - 0.6-1
- List all python packages in the setup.py
- Initial implementation of the execute step
- Vagrant Provider output and provider handling
- Relay API methods to instances in provision
- Simple localhost provisioner (#28)
- Implement shell discover, add a simple example
- Fix test path, discover in go(), adjust example
- Add run.sh for running the tests on guest
- Add default config for libvirt to use QEMU session

* Tue Oct 29 2019 Petr Šplíchal <psplicha@redhat.com> - 0.5-1
- Implement common --filter and --condition options
- Store step data during save()
- Common logging methods, improve run() output
- Implement common options and parent checking
- Sync the whole plan workdir to the guest
- Fix inheritance and enable --verbose mode.
- Rename the main metadata tree option to --root
- Adjust tests to skip provision, fix raw strings
- Move example Vagrantfiles to examples
- Implement ProvisionVagrant (#20)
- Implement tests.yaml creation in discover
- Implement 'tmt test export' with yaml support
- Support checking parent options, fix plan show -v
- Implement common methods status(), read(), write()
- Implement run() to easily execute in the workdir
- Implement DiscoverPlugin class, require step names
- Move workdir handling into the Common class
- Common class & filtering tests/plans for execution
- Improve step handling, remove global variables
- Fix 'tmt init --full' in a clean directory
- Better handle defaults and command line options
- Do not run systemd plan as it fetches remote repo
- Add documentation generated files to gitignore
- Get rid of the test attribute inconsistencies
- Fix various issues in localhost provisioner skeleton
- Update discover step story with example output
- Add an example of a shell discover step
- Add a simple smoke test story
- Add base class for provisioner
- Initial implementation of the discover step
- Allow creating tmt tree under an existing one
- Support multiple configs in Step.show()
- Support and document optional dependencies install
- Add an example of multiple configs
- Convert step data to list, add execute check
- Add --how option to provision command
- Move step classes into separate directories
- Implement class Run with workdir support
- Add a workdir structure example
- Separate metadata tree for L2 metadata examples
- Add stories covering the Metadata Specification
- Enable bash completion feature

* Thu Oct 17 2019 Petr Šplíchal <psplicha@redhat.com> - 0.4-1
- Add tests for 'tmt init', allow overwritting
- Use plural commands to prevent confusion [fix #10]
- Add a link to Packit & Testing Farm documentation
- Add a simple develop section to the readme
- Split cli stories into multiple files
- Cleanup convert example, simplify story example
- Implement initialization with creating examples
- Implement 'tmt {test,plan,story} show --verbose'
- Implement 'tmt story create', add basic templates
- Implement 'tmt plan create' plus initial templates
- Add a new story for creating plans (enable CI)
- Add basic rpm installation stories
- Show test steps summary in plan show if provided
- Add a Release Test Team installation tests example
- Suggest git-like moving forward in tasks
- Fix step names in 'tmt plan show' output
- Update documentation overview with latest changes
- Add story introduction, cleanup generated files
- Generate documentation for user stories
- Use raw string to prevent invalid escape sequence
- Test Management Tool, it's not metadata only
- Add a story for core option --debug
- Add a story for the mock shortcut [fix #5, fix #6]
- Add a story for core option --format
- Propose a dream for hands-free debugging
- Rename remaining testset occurences to plan
- Implement 'tmt plan lint' with initial checks

* Thu Oct 10 2019 Petr Šplíchal <psplicha@redhat.com> - 0.3-1
- Fix uncovered story filter logic, show total
- Rename testsets to plans, simplify playbooks
- Fix basic testset repo, install dependencies
- Implement 'tmt init', add the corresponding story
- Show overview of available tests, plans, stories
- Implement 'tmt story coverage', update coverage
- Implement 'tmt story --covered / --uncovered'
- Rename testsest to plan to avoid common prefix

* Wed Oct 09 2019 Petr Šplíchal <psplicha@redhat.com> - 0.2-1
- Enable Packit building and Testing Farm testing
- Provide one-letter versions for select options
- Implement 'tmt run --all' to run all test steps
- Support command abbreviation, add related stories
- Add the Quick Start Guide story to documention
- Add coverage options to tmt story ls and show
- Initialize metadata tree only when accessed
- Remove show functionality from the 'run' command
- Implement 'tmt test create' with basic templates
- Implement 'tmt test lint' with some basic checks
- Add user stories for core options and attributes
- Implement 'tmt story show', couple of adjustments
- Prevent alphabetical sorting of commands in help
- Move unit tests into a separate directory
- Align examples with the latest specification
- Implement 'tmt show' for test and testset
- Implement ls for test, testset and story commands
- Add 'tmt test create' command to user stories
- Add an initial set of basic tests
- Update cli user stories, add api & docs stories
- Add a couple of dreams for the bright future :-)

* Mon Sep 30 2019 Petr Šplíchal <psplicha@redhat.com> - 0.1-1
- Initial packaging
