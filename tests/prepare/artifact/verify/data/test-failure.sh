#!/bin/bash
set -ex

# Verify make is installed from tmt-artifact-shared
rpm -q make
dnf info --installed make | grep -E "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify make-devel is installed from tmt-artifact-shared
rpm -q make-devel
dnf info --installed make-devel | grep -E "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify diffutils is installed from fedora repo
rpm -q diffutils
dnf info --installed diffutils | grep -E "From repo(sitory)?\s*:\s*fedora"

echo "SUCCESS: All packages verified to be from expected repositories"
