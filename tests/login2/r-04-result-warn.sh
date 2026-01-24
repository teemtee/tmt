#!/bin/bash
# TEST-NAME: Result type variation - warn
# ====================
#
# WHAT THIS TESTS:
#   Tests that the --when warn condition correctly identifies and triggers
#   login based on test results with the warn type.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when warn -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step
#   - Login should trigger because at least one test has a warn result
#   - The warn result type is properly detected and acted upon
#
# KEY POINT:
#   This tests the warn result type specifically, demonstrating that
#   --when conditions properly identify and respond to warn results.
#
# TEST DATA:
#   - Creates one normal passing test
#   - Creates two tests with warnings
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section R-04

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_normal_test
        login2_create_two_warn_tests
    rlPhaseEnd

    rlPhaseStartTest "Result type - warn"
        rlRun -s "tmt run -ar provision -h container login --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
