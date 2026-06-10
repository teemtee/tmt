Name:       foo
Version:    1.4
Release:    1
BuildArch:  noarch
Summary:    Main test package
License:    none

%description
System package version (baseline)

%files

%package devel
Summary:    Main test sub-package
Requires:   foo-%{version} == %{version}-%{release}

%description devel
Version locked sub-package

%files devel
