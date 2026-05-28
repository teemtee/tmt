#!/bin/bash
set -ex

# Verify make is installed
rpm -q make

# Verify make came from the tmt-artifact-shared repository
dnf info --installed make | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify bar is installed
rpm -q bar

# Verify bar came from the test-bar repository
dnf info --installed bar | grep -Eq "From repo(sitory)?\s*:\s*test-bar"
