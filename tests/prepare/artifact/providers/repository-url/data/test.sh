#!/bin/bash
set -ex

# Verify bar is installed
rpm -q bar

# Verify bar came from the tmt-repo-default-0 repository
dnf info --installed bar | grep -Eq "From repo(sitory)?\s*:\s*tmt-repo-default-0"

# Verify the repository priority is set to default 50
dnf repoinfo tmt-repo-default-0 | grep -Eq "Priority\s*:\s*50"
