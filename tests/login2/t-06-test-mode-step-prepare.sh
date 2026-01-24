#!/bin/bash
# T-06: Login -t --step prepare (override)
# Expected: Login in prepare, not per-test in execute

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan true
        login2_create_test "test1" "true"
        login2_create_test "test2" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step prepare (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step prepare -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
