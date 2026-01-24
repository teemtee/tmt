#!/bin/bash
# TEST-NAME: Login with --step execute option
# ====================
#
# WHAT THIS TESTS:
#   Tests that login occurs during the execute step (after all tests complete),
#   not per-test and not in the finish step.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --step execute -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur exactly once at the end of the execute step
#   - Login should not be per-test (that requires -t flag)
#   - Login should not occur in the finish step
#
# KEY POINT:
#   This tests the --step option with execute, demonstrating that without
#   the -t flag, login happens once after all tests complete, not per-test.
#
# TEST DATA:
#   - Creates 3 normal tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-06

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Login --step execute"
        rlRun -s "tmt run -ar provision -h container login --step execute -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
