Name:       foo-ng
Version:    2.2
Release:    1
BuildArch:  noarch
Summary:    Main test package
License:    none

Provides:   foo
Obsoletes:  foo < 3.0-1

%description
Replacing package (not verified)

%files

%package devel
Summary:    Main test sub-package
Requires:   foo-ng-%{version} == %{version}-%{release}

%description devel
Version locked sub-package

%files devel
