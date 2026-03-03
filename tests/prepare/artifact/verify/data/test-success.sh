#!/bin/bash
set -ex

# Verify make is installed
rpm -q make

# Verify it came from the tmt-artifact-shared repository
dnf info --installed make | grep -E "From repo(sitory)?\s*:\s*tmt-artifact-shared"

echo "SUCCESS: Package verified to be from tmt-artifact-shared"
