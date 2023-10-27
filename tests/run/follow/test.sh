#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "tmt run --id $run &>/dev/null &" 0 "Start a tmt run in background"
        rlRun "sleep 1" 0 "Ignore logging during the first second"
        rlRun -s "timeout -s INT 5 tmt run --id $run --follow" 124 "Follow logs for 5 seconds"
        rlAssertGrep "step-01" $rlRun_LOG
        rlAssertGrep "step-02" $rlRun_LOG
        rlAssertNotGrep "step-09" $rlRun_LOG
        rlAssertNotGrep "step-10" $rlRun_LOG
        rlRun "wait $!" 0 "Wait until the run is finished"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
