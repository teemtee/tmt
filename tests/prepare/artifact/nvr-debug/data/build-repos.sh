#!/bin/bash
# Build two versions of a dummy RPM and create two local repos.
# Repo layout (created at /tmp/nvr-test/):
#   repo-high/  - contains dummy-nvr-test-1.0-1 (older version)
#   repo-low/   - contains dummy-nvr-test-2.0-1 (newer version)
# The names "high" and "low" refer to the priority assigned in the
# repo files: repo-high will be given a lower numeric priority value
# (i.e. higher importance) by the calling plan.

set -ex

PACKAGE="dummy-nvr-test"
REPO_BASE="/tmp/nvr-test"
REPO_HIGH="$REPO_BASE/repo-high"
REPO_LOW="$REPO_BASE/repo-low"
BUILD_DIR="/tmp/rpm-build-nvr-test"

dnf install -y rpm-build createrepo_c

mkdir -p "$REPO_HIGH" "$REPO_LOW"
mkdir -p "$BUILD_DIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Spec for v1.0 (goes into the high-priority repo)
cat > "$BUILD_DIR/SPECS/v1.spec" << 'SPECEOF'
Name:       dummy-nvr-test
Version:    1.0
Release:    1
Summary:    Dummy package for NVR priority testing
License:    MIT
BuildArch:  noarch

%description
Dummy package used to verify DNF5 repository-priority and NVR-based
package selection. This is version 1.0 placed in the high-priority repo.

%install

%files

%changelog
SPECEOF

# Spec for v2.0 (goes into the low-priority repo)
cat > "$BUILD_DIR/SPECS/v2.spec" << 'SPECEOF'
Name:       dummy-nvr-test
Version:    2.0
Release:    1
Summary:    Dummy package for NVR priority testing
License:    MIT
BuildArch:  noarch

%description
Dummy package used to verify DNF5 repository-priority and NVR-based
package selection. This is version 2.0 placed in the low-priority repo.

%install

%files

%changelog
SPECEOF

rpmbuild --define "_topdir $BUILD_DIR" -bb "$BUILD_DIR/SPECS/v1.spec"
rpmbuild --define "_topdir $BUILD_DIR" -bb "$BUILD_DIR/SPECS/v2.spec"

find "$BUILD_DIR/RPMS" -name "${PACKAGE}-1.0*.rpm" -exec cp {} "$REPO_HIGH/" \;
find "$BUILD_DIR/RPMS" -name "${PACKAGE}-2.0*.rpm" -exec cp {} "$REPO_LOW/" \;

createrepo_c "$REPO_HIGH"
createrepo_c "$REPO_LOW"

echo "Repos created at $REPO_BASE"
ls -la "$REPO_HIGH" "$REPO_LOW"
