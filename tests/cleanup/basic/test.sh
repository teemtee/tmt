#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run -vvv --id $run" 2 "Run failed during report step"
        rlAssertGrep "out: Prepare step executed" $rlRun_LOG
        rlRun -s "yq -e '.status == \"done\"' $run/plan/cleanup/step.yaml" 0 "Cleanup step was executed"
        rlAssertNotGrep "out: Finish step executed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
