Name:           tmt
Version:        0.0.0
Release:        %autorelease
Summary:        Test Management Tool

License:        MIT
URL:            https://github.com/teemtee/tmt
Source0:        %{pypi_source tmt}

BuildArch:      noarch
BuildRequires:  python3-devel

Requires:       git-core rsync sshpass

Recommends:     bash-completion

%py_provides    python3-tmt

%global _metapackage_description %{expand:
This is a metapackage bringing in extra dependencies for tmt.
It contains no code, just makes sure the dependencies are installed.}

%description
The tmt Python module and command line tool implement the test
metadata specification (L1 and L2) and allows easy test execution.

%pyproject_extras_subpkg -n tmt export-polarion
%pyproject_extras_subpkg -n tmt report-junit
%pyproject_extras_subpkg -n tmt report-polarion

%package -n     tmt+test-convert
Summary:        Dependencies required for tmt test import and export
Requires:       tmt == %{version}-%{release}
Requires:       make
Requires:       python3-bugzilla
Requires:       python3-nitrate
Requires:       python3-html2text
Requires:       python3-markdown

%description -n tmt+test-convert %_metapackage_description

%package -n     tmt+provision-container
Summary:        Dependencies required for tmt container provisioner
Requires:       tmt == %{version}-%{release}
Requires:       podman
Requires:       (ansible or ansible-collection-containers-podman)

%description -n tmt+provision-container %_metapackage_description

%package -n     tmt+provision-virtual
Summary:        Dependencies required for tmt virtual machine provisioner
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

%description -n tmt+provision-virtual %_metapackage_description

%package -n     tmt+provision-beaker
Summary:        Dependencies required for tmt beaker provisioner
Requires:       tmt == %{version}-%{release}
Requires:       python3-mrack-beaker

%description -n tmt+provision-beaker %_metapackage_description

%package -n     tmt+all
Summary:        Extra dependencies for the Test Management Tool
Provides:       tmt-all == %{version}-%{release}
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
mkdir -p %{buildroot}/etc/%{name}/
install -pm 644 %{name}/steps/provision/mrack/mrack* %{buildroot}/etc/%{name}/

%check
%pyproject_check_import

%files -n tmt -f %{pyproject_files}
%doc README.rst examples
%{_bindir}/tmt
%{_mandir}/man1/tmt.1.gz
%{_datadir}/bash-completion/completions/%{name}

%files -n tmt+provision-container -f %{_pyproject_ghost_distinfo}
%files -n tmt+provision-virtual -f %{_pyproject_ghost_distinfo}
%files -n tmt+test-convert -f %{_pyproject_ghost_distinfo}
%files -n tmt+provision-beaker -f %{_pyproject_ghost_distinfo}
%config(noreplace) %{_sysconfdir}/%{name}/mrack*
%files -n tmt+all -f %{_pyproject_ghost_distinfo}

%changelog
