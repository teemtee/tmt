#!/bin/bash
# TEST-NAME: Result type variation - fail
# ====================
#
# WHAT THIS TESTS:
#   Tests that the --when fail condition correctly identifies and triggers
#   login based on test results with the fail type.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step
#   - Login should trigger because at least one test has a fail result
#   - The fail result type is properly detected and acted upon
#
# KEY POINT:
#   This tests the fail result type specifically, demonstrating that
#   --when conditions properly identify and respond to fail results.
#
# TEST DATA:
#   - Creates one passing test
#   - Creates two failing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section R-02

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_two_fail_tests
    rlPhaseEnd

    rlPhaseStartTest "Result type - fail"
        rlRun -s "tmt run -ar provision -h container login --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
