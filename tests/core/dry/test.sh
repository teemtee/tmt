#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test debug/verbose levels"
        rlRun "tmt --feeling-safe run --dry -r"
        rlRun "tmt --feeling-safe run --dry -dvr"
        rlRun "tmt --feeling-safe run --dry -ddvvr"
        rlRun "tmt --feeling-safe run --dry -dddvvvr"
    rlPhaseEnd

    rlPhaseStartTest "Dry provision propagation"
        rlRun "tmt --feeling-safe run --all --remove provision --how virtual --dry"
    rlPhaseEnd
rlJournalEnd
