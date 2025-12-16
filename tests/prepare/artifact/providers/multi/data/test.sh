#!/bin/bash
set -ex

# Verify make is installed from koji.build
rpm -q make

# Verify docker-ce-cli is installed from the configured repository
rpm -q docker-ce-cli
