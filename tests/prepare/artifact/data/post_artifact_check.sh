#!/bin/bash

# Check that make was not already installed
if rpm -q make; then
  echo "Error: Make was installed before it was expected"
  exit 1
fi
# Check for shared  repository presence
REPO_FILE="/etc/yum.repos.d/tmt-artifact-shared.repo"
if [ ! -s "$REPO_FILE" ]; then
  echo "Error: Artifact repository definition not found or empty at $REPO_FILE"
  exit 1
fi
exit 0
