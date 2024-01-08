#!/bin/bash

set -ex

if [ "$STATE" = "enabled" ]; then
    for reponame in $REPOSITORIES; do
        dnf repoinfo "$reponame" | grep -E "^Repo-status[[:space:]]+: enabled"
    done
else
    for reponame in $REPOSITORIES; do
        (dnf repoinfo "$reponame" | grep -E "^Repo-status[[:space:]]+: disabled") || (dnf repoinfo "$reponame" | grep -E '^Total packages: 0')
    done
fi
