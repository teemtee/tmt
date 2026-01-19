#!/bin/bash
set -ex

# Verify make is installed
rpm -q make

# Verify make came from the tmt-artifact-shared repository
dnf info --installed make | grep -Eq "From repository\s*:\s*tmt-artifact-shared"

# Verify docker-ce-cli is installed
rpm -q docker-ce-cli

# Verify docker-ce-cli came from the docker-ce repository
dnf info --installed docker-ce-cli | grep -Eq "From repository :\s*docker-ce"
