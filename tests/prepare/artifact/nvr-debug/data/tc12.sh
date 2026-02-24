#!/bin/bash
# TC 1.2 - Same priority falls back to NVR comparison
# Both repos have priority=50.
# Repo A has v1.0, Repo B has v2.0.
# Expected: v2.0 is installed because it has the higher NVR.
set -ex

# Package must be installed (via require)
rpm -q dummy-nvr-test

# Same-priority repos: highest NVR wins, so v2.0 must be installed
rpm -q dummy-nvr-test | grep -E "^dummy-nvr-test-2\.0-"

# Confirm it was drawn from the repo that carries v2.0
dnf info --installed dummy-nvr-test | grep -Eq "From repo(sitory)?\s*:\s*test-same-priority-b"
