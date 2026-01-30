#!/bin/bash
set -ex

# Verify cowsay is installed (from remote URL)
rpm -q cowsay

# Verify cowsay came from the tmt-artifact-shared repository
dnf info --installed cowsay | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify figlet is installed (from local file)
rpm -q figlet

# Verify figlet came from the tmt-artifact-shared repository
dnf info --installed figlet | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify boxes is installed (from directory with multiple RPMs)
rpm -q boxes

# Verify boxes came from the tmt-artifact-shared repository
dnf info --installed boxes | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify fortune-mod is installed (from directory with multiple RPMs)
rpm -q fortune-mod

# Verify fortune-mod came from the tmt-artifact-shared repository
dnf info --installed fortune-mod | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
