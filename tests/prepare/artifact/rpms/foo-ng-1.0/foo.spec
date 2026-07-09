Name:       foo-ng
Version:    1.0
Release:    1
BuildArch:  noarch
Summary:    Main test package
License:    none

Provides:   foo
Obsoletes:  foo < 3.0-1

%description
Replacing system package

%files

%package devel
Summary:    Main test sub-package
Requires:   foo-ng-%{version} == %{version}-%{release}

Provides:   foo-devel
Obsoletes:  foo-devel < 3.0-1

%description devel
Version locked sub-package

%files devel
