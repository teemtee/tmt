#!/bin/bash
# Create four local repos from pre-built binary RPMs.
# Runs inside the container as a plan prepare step.
# Binary RPMs are built by test.sh and pushed here by tmt as part of the
# normal repo sync. Both test cases (tc11, tc12) share these repos within
# the same container.

set -ex

PACKAGE="dummy-nvr-test"
REPO_BASE="/tmp/nvr-test"

mkdir -p "$REPO_BASE/tc11-high" "$REPO_BASE/tc11-low" \
         "$REPO_BASE/tc12-a"   "$REPO_BASE/tc12-b"

# Populate repos from pre-built RPMs pushed by tmt.
cp "./rpms/${PACKAGE}-1.0"*.rpm "$REPO_BASE/tc11-high/"
cp "./rpms/${PACKAGE}-2.0"*.rpm "$REPO_BASE/tc11-low/"
cp "./rpms/${PACKAGE}-1.0"*.rpm "$REPO_BASE/tc12-a/"
cp "./rpms/${PACKAGE}-2.0"*.rpm "$REPO_BASE/tc12-b/"

createrepo_c "$REPO_BASE/tc11-high"
createrepo_c "$REPO_BASE/tc11-low"
createrepo_c "$REPO_BASE/tc12-a"
createrepo_c "$REPO_BASE/tc12-b"

# Copy .repo files to the repo base so the artifact provider can find them
# at a known path on the guest via repository-file:file:///tmp/nvr-test/*.repo
cp ./tc11-high.repo ./tc11-low.repo ./tc12-a.repo ./tc12-b.repo "$REPO_BASE/"
