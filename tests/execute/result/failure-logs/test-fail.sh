#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Failing beakerlib test"
        rlRun "echo \"Some output\""
        rlRun "false"
    rlPhaseEnd
rlJournalEnd
