#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run -vv --id $run --repeat 2"

        rlAssertGrep "Repeating plan 2 times." $rlRun_LOG
        rlAssertGrep "summary: 5 tests passed" $rlRun_LOG
        rlAssertGrep "total: 10 tests passed" $rlRun_LOG

        rlAssertExists "$run/plan-1/execute/data/guest/default-0/Test-1-1/output.txt"
        rlAssertExists "$run/plan-2/execute/data/guest/default-0/Test-1-1/output.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
