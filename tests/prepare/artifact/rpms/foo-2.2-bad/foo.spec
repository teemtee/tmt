Name:       foo
Version:    2.2
Release:    1
BuildArch:  noarch
Summary:    Main test package
License:    none

# Arbitrary broken dependency at install time
Requires:   some-non-existent-package

%description
Newer version (not verified, Broken)

%files

%package devel
Summary:    Main test sub-package
Requires:   foo-%{version} == %{version}-%{release}

%description devel
Version locked sub-package

%files devel
