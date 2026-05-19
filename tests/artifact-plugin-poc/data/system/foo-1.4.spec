Name:       foo
Version:    1.4
Release:    1
Summary:    Test package foo 1.4 (system repo)
License:    MIT
BuildArch:  noarch

%description
Test package for artifact-plugin DNF behaviour tests. Version 1.4 placed in
the system repo at priority=99 so artifact repo (priority=50) takes precedence.

%install
%files
%changelog
