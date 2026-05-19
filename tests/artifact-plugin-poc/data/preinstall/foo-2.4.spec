Name:       foo
Version:    2.4
Release:    1
Summary:    Test package foo 2.4 (pre-install via rpm -i)
License:    MIT
BuildArch:  noarch

%description
Test package for artifact-plugin tests. Installed directly via rpm -i --force
to simulate a package with unknown origin (no DNF swdb entry).

%install
%files
%changelog
