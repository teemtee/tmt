#!/bin/bash
# C-07: Login -t --when fail --step execute --step finish
# Expected: Login after each failed test (execute) + in finish

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --step execute --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --step execute --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
