#!/bin/bash
# TC 1.2 - Same priority falls back to NVR comparison
# Both repos at priority=50; highest NVR (v2.0) wins
set -ex

cp ./tc12-a.repo /etc/yum.repos.d/
cp ./tc12-b.repo /etc/yum.repos.d/

dnf install -y dummy-nvr-test

# Same priority: highest NVR wins, v2.0 must be installed
rpm -q dummy-nvr-test | grep -E "^dummy-nvr-test-2\.0-"
dnf repoquery --installed dummy-nvr-test --qf "%{from_repo}" | grep -Fx "test-same-priority-b"
