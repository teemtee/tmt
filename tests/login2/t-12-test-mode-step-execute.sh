#!/bin/bash
# T-12: Login -t --step execute (redundant)
# Expected: N logins (same as -t alone, redundant but should work)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test1" "true"
        login2_create_test "test2" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step execute (redundant)"
        rlRun -s "tmt run -ar provision -h container login -t --step execute -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
