#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest
        rlRun "false"
    rlPhaseEnd
    rlPhaseStartTest
        rlRun "exit 0"
    rlPhaseEnd
rlJournalEnd
