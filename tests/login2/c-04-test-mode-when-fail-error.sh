#!/bin/bash
# TEST-NAME: Test mode with multiple --when conditions
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) with multiple --when conditions results in
#   per-test login during execute for tests matching ANY condition (fail OR error).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail --when error -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur twice in execute step (after fail and error tests)
#   - Login should not occur after passing test
#   - Login should not occur in finish step
#
# KEY POINT:
#   In test mode, multiple --when conditions are OR'd together per-test.
#   Login occurs after each test that matches ANY condition, not just in finish.
#
# TEST DATA:
#   - Creates tests with pass, fail, and error results
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section C-04

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_fail_error_tests
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --when error"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
