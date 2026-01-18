#!/bin/bash
set -ex

# Verify make is installed
rpm -q make

# Verify it came from the tmt-artifact-shared repository
dnf info --installed make | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
