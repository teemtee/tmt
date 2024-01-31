#!/bin/bash

set -ex

if [[ "$STATE" == "enabled" ]]; then
    fips-mode-setup --check | grep -E '^FIPS mode is enabled'
else
    fips-mode-setup --check | grep -E '^FIPS mode is disabled'
fi
