#!/bin/bash
# TEST-NAME: Test mode edge case - all tests fail
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) with --when fail results in per-test login
#   after every test when ALL tests fail (all meet the condition).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur three times in execute step (after each failing test)
#   - Every test triggers login since all fail
#   - Login should not occur in finish step
#
# KEY POINT:
#   This tests the edge case where all tests match the --when condition,
#   demonstrating that login occurs after each test when all conditions are met.
#
# TEST DATA:
#   - Creates 3 failing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section E-02

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_fail_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail (all fail)"
        rlRun -s "tmt run -ar provision -h container login -t --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
