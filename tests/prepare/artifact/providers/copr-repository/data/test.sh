#!/bin/bash
set -ex

# Verify pyspread is installed
rpm -q pyspread

# Verify pyspread came from the copr repository
dnf info --installed pyspread | grep -Eq "From repo(sitory)?\s*:\s*copr:.*:mariobl:pyspread"
