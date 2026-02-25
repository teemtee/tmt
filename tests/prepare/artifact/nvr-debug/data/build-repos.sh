#!/bin/bash
# Build binary RPMs from pre-built SRPMs and create four local repos.
# Runs inside the container as a plan prepare step.
# SRPMs are committed in data/srpms/ (see build_srpms.sh) and pushed here
# by tmt as part of the normal repo sync.
# Both test cases (tc11, tc12) share these repos within the same container.

set -ex

PACKAGE="dummy-nvr-test"
BUILD_DIR="$(mktemp -d)"
REPO_BASE="/tmp/nvr-test"

dnf install -y rpm-build createrepo_c

mkdir -p "$REPO_BASE/tc11-high" "$REPO_BASE/tc11-low" \
         "$REPO_BASE/tc12-a"   "$REPO_BASE/tc12-b"

# Build binary RPMs from the host-built SRPMs for this container's distro.
rpmbuild --define "_topdir $BUILD_DIR" --rebuild ./srpms/${PACKAGE}-1.0*.src.rpm
rpmbuild --define "_topdir $BUILD_DIR" --rebuild ./srpms/${PACKAGE}-2.0*.src.rpm

# Populate repos using glob directly in cp.
cp "$BUILD_DIR/RPMS/noarch/${PACKAGE}-1.0"*.rpm "$REPO_BASE/tc11-high/"
cp "$BUILD_DIR/RPMS/noarch/${PACKAGE}-2.0"*.rpm "$REPO_BASE/tc11-low/"
cp "$BUILD_DIR/RPMS/noarch/${PACKAGE}-1.0"*.rpm "$REPO_BASE/tc12-a/"
cp "$BUILD_DIR/RPMS/noarch/${PACKAGE}-2.0"*.rpm "$REPO_BASE/tc12-b/"
rm -rf "$BUILD_DIR"

createrepo_c "$REPO_BASE/tc11-high"
createrepo_c "$REPO_BASE/tc11-low"
createrepo_c "$REPO_BASE/tc12-a"
createrepo_c "$REPO_BASE/tc12-b"
