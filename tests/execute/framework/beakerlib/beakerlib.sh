#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest
        rlRun "echo 'this should count as a pass'"
    rlPhaseEnd
rlJournalEnd
