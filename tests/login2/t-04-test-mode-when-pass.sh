#!/bin/bash
# T-04: Login -t --when pass
# Expected: Login only after passed tests, NOT in finish

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_two_pass_tests
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when pass"
        rlRun -s "tmt run -ar provision -h container login -t --when pass -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
