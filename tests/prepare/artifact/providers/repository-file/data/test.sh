#!/bin/bash
set -ex

# Verify bar is installed
rpm -q bar

# Verify it came from the test-bar.repo
dnf info --installed bar | grep -Eq "From repo(sitory)?\s*:\s*test-bar"
