Name:       foo-ng
Version:    2.4
Release:    1
BuildArch:  noarch
Summary:    Main test package
License:    none

Provides:   foo
Obsoletes:  foo < 3.0-1

# Arbitrary broken dependency at install time
Requires:   some-non-existent-package

%description
Replacing package in verified artifacts (Broken)

%files

%package devel
Summary:    Main test sub-package
Requires:   foo-ng-%{version} == %{version}-%{release}

%description devel
Version locked sub-package

%files devel
