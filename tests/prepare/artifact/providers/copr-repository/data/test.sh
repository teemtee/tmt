#!/bin/bash
set -ex

# Verify pyspread is installed
rpm -q bar

# Verify pyspread came from the copr repository
dnf info --installed bar | grep -Eq "From repo(sitory)?\s*:\s*copr:.*:lecris:_tmt_test"
