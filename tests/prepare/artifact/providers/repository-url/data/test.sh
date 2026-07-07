#!/bin/bash
set -ex

# Verify bar is installed
rpm -q bar

# Verify bar came from the tmt-repo-default-0 repository
dnf info --installed bar | grep -E "From repo(sitory)?\s*:\s*tmt-repo-default-0"
