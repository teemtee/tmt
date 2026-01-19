#!/bin/bash
set -ex

# Verify make is installed
rpm -q make

# Verify it came from the tmt-artifact-shared repository
dnf info --installed make | grep -Eq "From repository :\s*tmt-artifact-shared"
