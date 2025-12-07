#!/bin/bash

# Check that make was not already installed
if rpm -q make; then
  echo "Error: Make was already installed previously"
  exit 1
fi
# Check that the shared repository file does not exist yet
REPO_FILE="/etc/yum.repos.d/tmt-artifact-shared.repo"
if [ -f "$REPO_FILE" ]; then
  echo "Error: Artifact repository definition already exists at $REPO_FILE"
  exit 1
fi
exit 0
