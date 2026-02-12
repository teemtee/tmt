#!/bin/bash
set -ex

# Verify jq is installed (from directory with multiple RPMs)
rpm -q jq

# FIXME: The package should be installed from artifact shared or we should fail here
# with a proper error, We need to adjust this test when we send a fix for install code
# Check if host kernel matches container release (rawhide host has a newer kernel)
if uname -r | grep -q "\.fc$(rpm -E %{fedora})\."; then
    # Verify jq came from the tmt-artifact-shared repository
    dnf info --installed jq | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
else
    # On rawhide hosts, jq has incompatible deps and gets installed from updates
    dnf info --installed jq | grep -Eq "From repo(sitory)?\s*:\s*updates"
fi

# Verify nano is installed (from directory with multiple RPMs)
rpm -q nano

# Verify nano came from the tmt-artifact-shared repository
dnf info --installed nano | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
