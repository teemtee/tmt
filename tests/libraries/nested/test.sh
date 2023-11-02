#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup "Prepare test"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run -ar discover -vvvddd report -vvv 2>&1 >/dev/null"
        rlAssertGrep "Creating file 'fooo'" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
