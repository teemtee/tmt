#!/bin/bash
set -ex

# Verify docker-ce-cli is installed
rpm -q docker-ce-cli

# Verify docker-ce-cli came from the tmt-repo-default-0 repository
dnf info --installed docker-ce-cli | grep -Eq "From repo(sitory)?\s*:\s*tmt-repo-default-0"

# Verify the repository priority is set to default 50
dnf repoinfo tmt-repo-default-0 | grep -Eq "Priority\s*:\s*50"
