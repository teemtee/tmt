#!/bin/bash
# M-08: Login -t --when fail --when error --step finish
# Expected: Login after each failed/errored test (execute) + in finish

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_fail_error_tests
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --when error --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --when error --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlAssertGreaterOrEqual "Should have at least 2 logins" "$(grep -c "interactive" "$rlRun_LOG")" "2"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
