#!/bin/bash

if ! rpm -q bar; then
  echo "Error: bar was not installed"
  exit 1
fi
