#!/bin/bash
set -ex

# Verify make is installed from koji.build
rpm -q make

# Verify it came from the tmt-artifact-shared repository
dnf info --installed make | grep -q tmt-artifact-shared
