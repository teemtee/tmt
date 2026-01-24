#!/bin/bash
# TEST-NAME: Test mode with multiple --when conditions (pass and fail)
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) with multiple --when conditions (pass and fail)
#   results in per-test login during execute for tests matching ANY condition.
#   Since pass and fail cover all tests here, login occurs after every test.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when pass --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur twice in execute step (after each test)
#   - All tests match either pass or fail condition
#   - Login should not occur in finish step
#
# KEY POINT:
#   In test mode, multiple --when conditions are OR'd together per-test.
#   When conditions cover all test outcomes (pass/fail), login occurs
#   after every test.
#
# TEST DATA:
#   - Creates one passing test
#   - Creates one failing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section C-10

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when pass --when fail"
        rlRun -s "tmt run -ar provision -h container login -t --when pass --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
