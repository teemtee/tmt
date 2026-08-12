#!/bin/bash
set -ex

# Verify bar is installed
rpm -q bar

# Verify it came from the test-bar.repo (or test-bar-local.repo on CentOS 7)
if command -v dnf >/dev/null 2>&1; then
    dnf info --installed bar | grep -Eq "From repo(sitory)?\s*:\s*test-bar"
else
    yum info installed bar | grep -Eq "From repo(sitory)?\s*:\s*test-bar-local"
fi
