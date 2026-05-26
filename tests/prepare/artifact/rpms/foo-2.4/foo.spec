Name:       foo
Version:    2.4
Release:    1
BuildArch:  noarch
Summary:    Main test package
License:    none

%description
Newer version in verified artifacts

%files

%package devel
Summary:    Main test sub-package
Requires:   foo-%{version} == %{version}-%{release}

%description devel
Version locked sub-package

%files devel
