#!/bin/bash
# TEST-NAME: Result type variation - info
# ====================
#
# WHAT THIS TESTS:
#   Tests that the --when info condition correctly identifies and triggers
#   login based on test results with the info type (tests with info messages).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when info -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step
#   - Login should trigger because at least one test has info messages
#   - The info result type is properly detected and acted upon
#
# KEY POINT:
#   This tests the info result type specifically, demonstrating that
#   --when conditions properly identify and respond to tests that produce
#   informational messages (typically stderr output with "info:" prefix).
#
# TEST DATA:
#   - Creates one normal passing test
#   - Creates two tests with info messages
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section R-05

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_normal_test
        # Create two info tests
        login2_create_test "info1" "echo \"info: This is an info message\" >&2; true" "test: echo \"info: message\"; true"
        login2_create_test "info2" "echo \"info: More info\" >&2; true" "test: echo \"info: message2\"; true"
    rlPhaseEnd

    rlPhaseStartTest "Result type - info"
        rlRun -s "tmt run -ar provision -h container login --when info -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
