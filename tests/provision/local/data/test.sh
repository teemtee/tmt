#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test tmt-file-submit"
        rlRun "echo Hello"
    rlPhaseEnd
rlJournalEnd
