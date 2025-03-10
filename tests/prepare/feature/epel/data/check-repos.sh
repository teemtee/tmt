#!/bin/bash

set -ex

pkgmgr=$(dnf --version > /dev/null 2>&1 && echo dnf || echo yum)

STATE=${STATE:-"enabled"}
REPOSITORIES=${REPOSITORIES:-"epel epel-debuginfo epel-source"}

for reponame in $REPOSITORIES; do
    if [[ "$STATE" == "enabled" ]]; then
        $pkgmgr repoinfo "$reponame" | grep -E "^Repo-status[[:space:]]+: enabled"
    else
        # XXX: why do we check 'Total packages: 0' if it fails to check 'Repo-status'?
        ($pkgmgr repoinfo "$reponame" | grep -E "^Repo-status[[:space:]]+: disabled") || \
            ($pkgmgr repoinfo "$reponame" | grep -E '^Total packages: 0')
    fi
done
