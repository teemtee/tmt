#!/bin/bash
# TEST-NAME: Test mode with --when error option
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) combined with conditional login (--when error)
#   results in per-test login during execute step, not in finish step.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when error -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur once in execute step (after each errored test)
#   - Login should not occur in finish step
#   - Only tests with error results should trigger login
#
# KEY POINT:
#   The -t flag means per-test login during execute. Combined with --when error,
#   it should login only after tests that error, and should NOT also login in finish.
#   This tests the fix for issue #1918 where -t was causing duplicate login.
#
# TEST DATA:
#   - Creates one normal passing test
#   - Creates one test that errors
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section T-03

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_normal_test
        login2_create_error_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when error"
        rlRun -s "tmt run -ar provision -h container login -t --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
