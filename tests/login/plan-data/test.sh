#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
    rlPhaseEnd

    rlPhaseStartTest "Test running all steps"
        # Log in at the end of prepare, execute and finish
        rlRun "tmt run --all --id $run provision --how $PROVISION_HOW \
            login --step prepare --step execute --step finish --command 'ls -l ../data'"

        # Check that generated data are correctly fetched
        for step in prepare execute finish; do
            rlAssertGrep "hi" "$run/plan/data/$step"
        done
    rlPhaseEnd

    rlPhaseStartTest "Test just provision, finish and cleanup"
        rlRun "tmt run --id $run --scratch \
            provision --how $PROVISION_HOW \
            finish \
            login --command 'ls -l ../data' \
            cleanup"
        rlAssertGrep "hi" "$run/plan/data/finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
