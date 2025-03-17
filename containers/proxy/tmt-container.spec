Name:           tmt-container
Version:        1.0
Release:        1%{?dist}
Summary:        Test Management Tool (container-based)
License:        MIT

Requires:       podman
Requires:       git-core
Requires:       rsync
Requires:       sshpass
Requires:       ansible-core

BuildArch:      noarch

%description
This package provides tmt command that runs inside a container with all dependencies installed.

%prep
# Nothing to do

%build
# Nothing to build

%install
mkdir -p %{buildroot}%{_bindir}

# Install the proxy script
install -m 755 %{_sourcedir}/tmt-proxy.sh %{buildroot}%{_bindir}/tmt

%files
%{_bindir}/tmt

%changelog
%autochangelog
