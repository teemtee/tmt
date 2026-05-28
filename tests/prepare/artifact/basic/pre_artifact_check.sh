#!/bin/bash

# Check that bar was not already installed
if rpm -q bar; then
  echo "Error: bar was already installed previously"
  exit 1
fi
exit 0
