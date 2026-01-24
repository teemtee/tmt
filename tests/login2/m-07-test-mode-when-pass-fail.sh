#!/bin/bash
# TEST-NAME: Test mode with --when pass and --when fail
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) with multiple --when conditions (pass and fail)
#   results in per-test login during execute for all tests (since all tests
#   either pass or fail).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when pass --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur three times in execute step (after each test)
#   - All tests match either pass or fail condition
#   - Login should not occur in finish step
#
# KEY POINT:
#   In test mode, when --when conditions cover all test outcomes (pass/fail),
#   login occurs after every test. This is equivalent to using -t without conditions.
#
# TEST DATA:
#   - Creates two passing tests and one failing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section M-07

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_two_pass_and_fail_tests
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when pass --when fail"
        rlRun -s "tmt run -ar provision -h container login -t --when pass --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
