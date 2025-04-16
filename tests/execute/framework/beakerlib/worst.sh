#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "false"
    rlPhaseEnd
    rlPhaseStartTest
        rlRun "true"
    rlPhaseEnd
    rlPhaseStartTest
        rlRun "false"
    rlPhaseEnd
    rlPhaseStartCleanup
        rlRun "false"
    rlPhaseEnd
rlJournalEnd
