#!/bin/bash
set -ex

# Verify make is installed from koji.build
rpm -q make

# Install docker-ce-cli from the configured repository
dnf install -y docker-ce-cli

# Verify docker-ce-cli is installed
rpm -q docker-ce-cli
