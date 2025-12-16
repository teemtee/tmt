#!/bin/bash
set -ex

# Install docker-ce-cli from the configured repository
dnf install -y docker-ce-cli

# Verify it's installed
rpm -q docker-ce-cli
