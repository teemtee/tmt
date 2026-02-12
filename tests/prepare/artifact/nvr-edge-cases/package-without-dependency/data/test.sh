#!/bin/bash
set -ex

# Verify jq is installed (from directory with multiple RPMs)
rpm -q jq

# TODO: When install of a package from tmt-artifact-shared fails (e.g., due to
# incompatible deps), the plugin should throw an error instead of silently
# falling back to system repos. Adjust this test when that fix is implemented.
# On rawhide hosts, downloaded packages have incompatible deps and dnf falls back
# to installing jq from updates/fedora instead of the artifact repo.
if [ "$HOST_IS_RAWHIDE" = "yes" ]; then
    dnf info --installed jq | grep -Eq "From repo(sitory)?\s*:\s*(updates|fedora)"
else
    dnf info --installed jq | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
fi

# Verify nano is installed (from directory with multiple RPMs)
rpm -q nano

# Verify nano came from the tmt-artifact-shared repository
dnf info --installed nano | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
