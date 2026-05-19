Name:       foo-ng
Version:    1.4
Release:    1
Summary:    Test package foo-ng 1.4 (provides and obsoletes foo)
License:    MIT
BuildArch:  noarch
Provides:   foo = 1.4-1
Obsoletes:  foo < 1.4

%description
Replacement for foo. Used in the obsoletes+allowerasing test to verify that
installing the original foo package requires --allowerasing when foo-ng is
installed.

%install
%files
%changelog
