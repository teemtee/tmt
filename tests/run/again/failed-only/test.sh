#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "data=\$(mktemp -d)" 0 "Create data directory"
        rlRun "cp data/* $data"
        rlRun "pushd $data"
        rlRun "tmt init"
    rlPhaseEnd

    rlPhaseStartTest "Test basic run failed tests again scenario is working"
        rlRun -s "tmt run --all --scratch --id $run" 1 "Run tests, some fail"
        rlAssertGrep "total: 2 tests passed and 2 tests failed" $rlRun_LOG

        rlRun "sed -i 's/false/true/g' *" 0 "Fix the test"

        rlRun -s "tmt run --all --again --id $run tests --failed-only" 0 "Rerun failed tests"
        rlAssertGrep "1 test selected" $rlRun_LOG
        rlAssertGrep "total: 4 tests passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test another run with again does not execute anything"
        rlRun -s "tmt run --all --again --id $run tests --failed-only" 0 "Rerun failed tests again"
        rlAssertGrep "0 tests selected" $rlRun_LOG
        rlAssertNotGrep "1 tests selected" $rlRun_LOG
        rlAssertGrep "total: 4 tests passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run $data" 0 "Remove run and data directories"
    rlPhaseEnd
rlJournalEnd
