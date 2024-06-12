Name: demo
Version: 1.0
Summary: Trying discover with applied patches
Release: 1
License: MIT
BuildArch: noarch

%description
Some tests are being added by patches, lets discover them correctly

%prep
%autosetup -n package-src

%build

%install

%changelog
* Thu Jun 1 2023 Lukas Zachar <lzachar@redhat.com> 0.1-1
- Initial version
