#!/bin/bash
# Create local repos from pre-built binary RPMs.
# Runs inside the container as a plan prepare step (order 40).
# Binary RPMs are built by test.sh and pushed here by tmt as part of the
# normal repo sync. The .repo files are read from the controller by the
# artifact provider (order 50) and installed to /etc/yum.repos.d/.
#
# Usage: build-repos.sh <full-package-name:repo-name>...
# Example: build-repos.sh dummy-nvr-test-1.0-1:tc11-high dummy-nvr-test-2.0-1:tc11-low

set -ex

REPO_BASE="/tmp/nvr-test"

for spec in "$@"; do
    package="${spec%%:*}"
    repo="${spec#*:}"
    mkdir -p "$REPO_BASE/$repo"
    cp "./rpms/${package}"*.rpm "$REPO_BASE/$repo/"
    createrepo_c "$REPO_BASE/$repo"
done
