#!/bin/bash
set -ex

# Verify jq is installed (from directory with multiple RPMs)
rpm -q jq

# Verify jq came from the tmt-artifact-shared repository
dnf info --installed jq | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify nano is installed (from directory with multiple RPMs)
rpm -q nano

# Verify nano came from the tmt-artifact-shared repository
dnf info --installed nano | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
