#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    # The OUTPUTFILE variable is only supported in the
    # restraint-compatible mode.

    rlPhaseStartTest "Test /plans/compatible"
        rlRun -s "tmt run -vvv --id $run plan --name /plans/compatible tests -n /tmt-report-result" 1
        rlRun "grep -A2 'pass /good-with-log' $rlRun_LOG | grep fine.txt"
        rlRun "grep -A2 'pass /good-with-var' $rlRun_LOG | grep fine.txt"
        rlRun "grep -A2 'fail /bad-with-log'  $rlRun_LOG | grep wrong.txt"
        rlRun "grep -A2 'fail /bad-with-var'  $rlRun_LOG | grep wrong.txt"
        rlRun -s "tmt run -vvv --id $run plan --name /plans/compatible tests -n /env-var" 1
        rlAssertGrep "TMT_RESTRAINT_COMPATIBLE=1" "$rlRun_LOG"
        rlAssertGrep "RSTRNT_TASKNAME=/env-var" "$rlRun_LOG"
    rlPhaseEnd

    # In the incompatible mode the OUTPUTFILE variable should be
    # ignored and no output file should be displayed.

    for plan in "/plans/default" "/plans/incompatible"; do
        rlPhaseStartTest "Test $plan"
            rlRun -s "tmt run -vvv --id $run plan --name $plan tests -n /tmt-report-result" 1
            rlRun "grep -A2 'pass /good-with-log' $rlRun_LOG | grep fine.txt"
            rlRun "grep -A2 'pass /good-with-var' $rlRun_LOG | grep txt" 1
            rlRun "grep -A2 'fail /bad-with-log'  $rlRun_LOG | grep wrong.txt"
            rlRun "grep -A2 'fail /bad-with-var'  $rlRun_LOG | grep txt" 1
            rlRun -s "tmt run -vvv --id $run plan --name $plan tests -n /env-var" 1
            rlAssertGrep "TMT_RESTRAINT_COMPATIBLE=0" "$rlRun_LOG"
            rlAssertNotGrep "RSTRNT_TASKNAME=" "$rlRun_LOG"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
