#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Run all steps"
        rlRun "tmt run --id $run plan --name one"
        rlAssertExists "$run/plans/one"
        rlAssertNotExists "$run/plans/two"
    rlPhaseEnd

    rlPhaseStartTest "Check the last run report"
        rlRun "tmt run --last report -v"
        rlAssertExists "$run/plans/one"
        rlAssertNotExists "$run/plans/two"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
