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
        plan="/plans/compatible"
        rlRun -s "tmt run --scratch -vvv --id $run plans -n $plan tests -n /test/tmt-report-result" 1
        rlRun "grep -A2 'pass /good-with-log' $rlRun_LOG | grep fine.txt"
        rlRun "grep -A2 'pass /good-with-var' $rlRun_LOG | grep fine.txt"
        rlRun "grep -A2 'fail /bad-with-log'  $rlRun_LOG | grep wrong.txt"
        rlRun "grep -A2 'fail /bad-with-var'  $rlRun_LOG | grep wrong.txt"
        rlRun "tmt run --scratch --id $run plans -n $plan tests -n /test/env-var"
        test_log="$run$plan/execute/data/guest/default-0/test/env-var-1/output.txt"
        rlAssertGrep "^TMT_RESTRAINT_COMPATIBLE=1$" "$test_log"
        rlAssertGrep "^RSTRNT_TASKNAME=/test/env-var$" "$test_log"
    rlPhaseEnd

    # In the incompatible mode the OUTPUTFILE variable should be
    # ignored and no output file should be displayed.

    for plan in "/plans/default" "/plans/incompatible"; do
        rlPhaseStartTest "Test $plan"
            rlRun -s "tmt run --scratch -vvv --id $run plans -n $plan tests -n /test/tmt-report-result" 1
            rlRun "grep -A2 'pass /good-with-log' $rlRun_LOG | grep fine.txt"
            rlRun "grep -A2 'pass /good-with-var' $rlRun_LOG | grep txt" 1
            rlRun "grep -A2 'fail /bad-with-log'  $rlRun_LOG | grep wrong.txt"
            rlRun "grep -A2 'fail /bad-with-var'  $rlRun_LOG | grep txt" 1
            rlRun "tmt run --scratch --id $run plans -n $plan tests -n /test/env-var"
            test_log="$run$plan/execute/data/guest/default-0/test/env-var-1/output.txt"
            rlAssertGrep "^TMT_RESTRAINT_COMPATIBLE=0$" "$test_log"
            rlAssertNotGrep "^RSTRNT_TASKNAME=" "$test_log"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
