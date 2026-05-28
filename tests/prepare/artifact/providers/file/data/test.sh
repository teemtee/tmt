#!/bin/bash
set -ex

# verify the package is installed
rpm -q bar
# verify package came from the tmt-artifact-shared repository
dnf info --installed bar | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
