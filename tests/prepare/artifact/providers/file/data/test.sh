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

# Verify jq is installed (from directory with multiple RPMs)
rpm -q jq

# Verify jq came from the tmt-artifact-shared repository
dnf info --installed jq | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"

# Verify nano is installed (from directory with multiple RPMs)
rpm -q nano

# Verify nano came from the tmt-artifact-shared repository
dnf info --installed nano | grep -Eq "From repo(sitory)?\s*:\s*tmt-artifact-shared"
