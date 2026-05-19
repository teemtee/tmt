Name:       foo
Version:    1.1
Release:    1
Summary:    Test package foo 1.1 (pre-install via rpm -i)
License:    MIT
BuildArch:  noarch

%description
Test package for artifact-plugin tests. Installed directly via rpm -i --force
to simulate a package with unknown origin (no DNF swdb entry).

%install
%files
%changelog
