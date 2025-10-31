#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test recipe loading with no dependencies"
        rlRun -s "tmt run -vvv --scratch --id $run --recipe simple.yaml"
        rlAssertGrep "name: discover-fmf" $rlRun_LOG
        rlAssertGrep "name: discover-shell" $rlRun_LOG
        rlAssertGrep "summary: 3 tests selected" $rlRun_LOG
        rlAssertGrep "pass /discover-fmf/tests/first" $rlRun_LOG
        rlAssertGrep "pass /discover-fmf/tests/second" $rlRun_LOG
        rlAssertGrep "pass /discover-shell/shell-test" $rlRun_LOG
        rlAssertGrep "summary: 3 tests executed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
