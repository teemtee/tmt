#!/bin/bash
# TEST-NAME: Edge case - test mode with single test
# ====================
#
# WHAT THIS TESTS:
#   Tests that -t flag works correctly with a single test, matching the
#   exact scenario described in GitHub Issue #1918.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t -c true
#
# EXPECTED BEHAVIOR:
#   - With a single test and -t flag, login should occur exactly once
#   - Login should occur after the test in execute step
#   - Should NOT login again in finish step (this is the bug being fixed)
#   - The -t flag implicitly adds --step execute to prevent duplicate login
#
# KEY POINT:
#   This test matches the exact scenario from Issue #1918 where the user
#   reported: "I have plan with one test, run tmt run login -t however
#   there is an additional login in the finish step."
#   The test verifies that with the fix, only ONE login occurs (in execute),
#   not TWO (execute + finish).
#
# TEST DATA:
#   - Creates exactly 1 passing test (matching the issue description)
#
# SEE ALSO:
#   GitHub Issue #1918 - https://github.com/teemtee/tmt/issues/1918
#   TEST_SUMMARY.md - Section E-14

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test1" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t with single test"
        rlRun -s "tmt run -ar provision -h container login -t -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep -c interactive" 0 "Login in execute"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
