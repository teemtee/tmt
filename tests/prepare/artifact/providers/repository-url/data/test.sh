#!/bin/bash
set -ex

# Verify code is installed
rpm -q code

# Verify code came from the tmt-repo-default-0 repository
dnf info --installed code | grep -Eq "From repo(sitory)?\s*:\s*tmt-repo-default-0"

# Verify the repository priority is set to default 50
dnf repoinfo tmt-repo-default-0 | grep -Eq "Priority\s*:\s*50"
