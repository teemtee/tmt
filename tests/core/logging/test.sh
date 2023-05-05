#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Logging topics"
        rlRun -s "tmt -dddd plan show /plans/features/core > /dev/null"
        rlAssertNotGrep "key source" $rlRun_LOG
        rlAssertNotGrep "normalized fields" $rlRun_LOG

        rlRun -s "tmt --log-topic=key-normalization -dddd plan show /plans/features/core > /dev/null"
        rlAssertGrep "key source" $rlRun_LOG
        rlAssertGrep "normalized fields" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
    rlPhaseEnd
rlJournalEnd
