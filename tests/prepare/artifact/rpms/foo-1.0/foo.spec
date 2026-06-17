Name:       foo
Version:    1.0
Release:    1
BuildArch:  noarch
Summary:    Main test package
License:    none

%description
Pre-installed version, lower than current system package (foo-1.4)

%files

%package devel
Summary:    Main test sub-package
Requires:   foo-%{version} == %{version}-%{release}

%description devel
Version locked sub-package

%files devel
