#!/bin/bash
# TC 1.1 - Repository priority overrides package version
# High-priority (priority=1) repo has v1.0.
# Low-priority  (priority=100) repo has v2.0.
# Expected: v1.0 is installed because repo priority wins.
set -ex

# Package must be installed (via require)
rpm -q dummy-nvr-test

# Priority=1 repo wins: v1.0 must be installed, not v2.0
rpm -q dummy-nvr-test | grep -E "^dummy-nvr-test-1\.0-"

# Confirm it was drawn from the high-priority repository
dnf info --installed dummy-nvr-test | grep -Eq "From repo(sitory)?\s*:\s*test-high-priority"
