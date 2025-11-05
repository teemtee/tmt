#!/bin/bash

# Check that make was not already installed
if rpm -q make; then
  echo "Error: Make was installed before it was expected"
  exit 1
fi
# TODO: Check for repository presence
exit 0
