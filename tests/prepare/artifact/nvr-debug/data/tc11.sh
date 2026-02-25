#!/bin/bash
# TC 1.1 - Repository priority overrides package version
# priority=30 repo (v1.0) beats priority=50 repo (v2.0)
set -ex

cp ./tc11-high.repo /etc/yum.repos.d/
cp ./tc11-low.repo  /etc/yum.repos.d/

dnf install -y dummy-nvr-test

# priority=30 repo wins: v1.0 must be installed
rpm -q dummy-nvr-test | grep -E "^dummy-nvr-test-1\.0-"
dnf repoquery --installed dummy-nvr-test --qf "%{from_repo}" | grep -Fx "test-high-priority"

# Cleanup for tc12
dnf remove -y dummy-nvr-test
rm -f /etc/yum.repos.d/tc11-high.repo /etc/yum.repos.d/tc11-low.repo
