#!/bin/bash
# TC 1.2 - Same priority falls back to NVR comparison
# Both repos at priority=50; highest NVR (v2.0) wins
set -ex

# Same priority: highest NVR wins, v2.0 must be installed
rpm -q dummy-nvr-test | grep -E "^dummy-nvr-test-2\.0-"
dnf repoquery --installed dummy-nvr-test --qf "%{from_repo}" | grep -Fx "test-same-priority-b"
