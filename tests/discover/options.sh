#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'pushd data'
        rlRun 'set -o pipefail'
    rlPhaseEnd

    rlPhaseStartTest 'tmt run discover --how=fmf --help'
        rlRun -s 'tmt run discover --how fmf --help'
        rlAssertGrep 'Discover available tests from fmf metadata' $rlRun_LOG
        for option in url ref path test filter fmf-id; do
            rlAssertGrep "--$option" "$rlRun_LOG"
        done
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'popd'
    rlPhaseEnd
rlJournalEnd
