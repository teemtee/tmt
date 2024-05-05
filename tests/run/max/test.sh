#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run -vv --id $run --max 3"
        rlAssertGrep "Splitting plan to batches of 3 tests." $rlRun_LOG
        rlAssertGrep "3 tests selected" $rlRun_LOG
        rlAssertGrep "summary: 3 tests passed" $rlRun_LOG
        rlAssertGrep "2 tests selected" $rlRun_LOG
        rlAssertGrep "summary: 2 tests passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
