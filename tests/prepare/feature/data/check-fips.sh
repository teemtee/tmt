#!/bin/bash

set -ex

# XXX: How to get the provision method (i.e. the type of the guest)
# if [[ $PROVISION_METHOD == "container" || $PROVISION_METHOD == "local" ]]; then
#     echo "Provision method \"$PROVISION_METHOD\" is unsupported."
#     exit 0
# fi
out=$(systemd-detect-virt 2> /dev/null)
if [[ -z "$out" ]]; then
    echo "Container is unsupported."
    exit 0
fi

if [[ "$STATE" == "enabled" ]]; then
    fips-mode-setup --check | grep -E '^FIPS mode is enabled'
else
    fips-mode-setup --check | grep -E '^FIPS mode is disabled'
fi
