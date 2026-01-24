#!/bin/bash
# E-11: Login -t --step report (override)
# Expected: Login in report step, NOT per-test in execute

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan_with_report
        login2_create_test "test1" "true"
        login2_create_test "test2" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step report (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step report -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
