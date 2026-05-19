Name:       foo-devel
Version:    1.1
Release:    1
Summary:    Test package foo-devel 1.1 (strict dep on foo = 1.1-1)
License:    MIT
BuildArch:  noarch
Requires:   foo = 1.1-1

%description
Development headers for foo 1.1. Has a strict Requires: foo = 1.1-1 to force
a transitive downgrade of foo from 1.4 to 1.1 when foo-devel-1.1 is installed.

%install
%files
%changelog
