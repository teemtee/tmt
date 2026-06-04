#!/bin/bash

# Check that bar was not already installed
if rpm -q bar; then
  echo "Error: bar was installed before it was expected"
  exit 1
fi
exit 0
