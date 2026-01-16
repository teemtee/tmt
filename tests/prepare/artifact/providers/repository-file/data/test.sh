#!/bin/bash
set -ex

# Verify docker-ce-cli is installed
rpm -q docker-ce-cli

# Verify it came from the docker-ce repository
dnf info --installed docker-ce-cli | grep -Eq "From repo.*docker-ce"
