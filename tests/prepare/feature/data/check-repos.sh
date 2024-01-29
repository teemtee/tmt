#!/bin/bash

set -ex

pkgmgr=$(dnf --version > /dev/null 2>&1 && echo dnf || echo yum)

STATE=${STATE:-"enabled"}
REPOSITORIES=${REPOSITORIES:-"epel epel-debuginfo epel-source"}

if [[ "$STATE" == "enabled" ]]; then
    for reponame in $REPOSITORIES; do
        $pkgmgr repoinfo "$reponame" | grep -E "^Repo-status[[:space:]]+: enabled"
    done
else
    for reponame in $REPOSITORIES; do
        ($pkgmgr repoinfo "$reponame" | grep -E "^Repo-status[[:space:]]+: disabled") || \
            ($pkgmgr repoinfo "$reponame" | grep -E '^Total packages: 0')
    done
fi
