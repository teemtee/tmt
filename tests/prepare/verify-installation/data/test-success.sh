#!/bin/bash
set -ex

# Verify make is installed
rpm -q make

# Verify it came from the tmt-artifact-shared repository
dnf info --installed make | grep -E "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify make-devel is installed
rpm -q make-devel

# Verify it came from the tmt-artifact-shared repository
dnf info --installed make-devel | grep -E "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify diffutils is installed
rpm -q diffutils

# Verify it came from the fedora repository
dnf info --installed diffutils | grep -E "From repo(sitory)?\s*:\s*fedora"

echo "SUCCESS: All packages verified to be from expected repositories"
