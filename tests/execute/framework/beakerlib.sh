#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd beakerlib"
    rlPhaseEnd

    # beakerlib directory: run-xxx/plans/features/steps/execute/execute/data/guest/default-0/tests/execute/framework/beakerlib-1
    # test should be as folowing:

    # all possible outcomes in TESTRESULT_RESULT_STRING (out of ['pass', 'fail', 'info', 'warn', 'error', 'skip', 'pending'])

    # multiple rlPhase outcomes - the worst is the result

    # raise + "Invalid partial custom result '{spec}'" (TESTRESULT_RESULT_STRING is not one of the aforementioned)

    # error + note "TestResults FileError" (unable to open 'TestResults' file)

    # error + note "Result/State missing" (no TESTRESULT_RESULT_STRING/TESTRESULT_STATE in 'TestResults' file) 
    # rlRun exit will create TESTRESULT_STATE=incomplete

    # error + note "timeout" (exit code 124)

    # error + note "pidfile locking" (exit codes 122/123)

    # error + note "State '{state}'" (TESTRESULT_STATE != complete)

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
