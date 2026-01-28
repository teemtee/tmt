#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test recipe loading with library dependencies"
        rlRun -s "tmt run -vvv --scratch --id $run --recipe simple.yaml plan -n /plans/simple"
        rlAssertGrep "name: discover-fmf" $rlRun_LOG
        rlAssertGrep "name: discover-shell" $rlRun_LOG
        rlAssertGrep "summary: 2 tests selected" $rlRun_LOG
        rlAssertGrep "pass /discover-fmf/tests/first" $rlRun_LOG
        rlAssertGrep "pass /discover-shell/shell-test" $rlRun_LOG
        rlAssertGrep "summary: 2 tests executed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test recipe loading with remote repository"
        rlRun -s "tmt run -vvv --scratch --id $run --recipe remote.yaml plan -n /plans/remote"
        rlAssertGrep "summary: 1 test selected" $rlRun_LOG
        rlAssertGrep "pass /tests/one" $rlRun_LOG
        rlAssertGrep "summary: 1 test executed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test recipe loading with non-existent plan"
        rlRun "temp=\$(mktemp -d)" 0 "Create temporary directory"
        rlRun "cp -r .fmf simple.yaml $temp"
        rlRun "pushd $temp"
        rlRun -s "tmt run -vvv --scratch --id $run --recipe simple.yaml" 2 "Remote plan is not in the recipe"
        rlAssertGrep "Plan '/default/plan' not found in the recipe" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
