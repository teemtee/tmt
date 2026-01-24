#!/bin/bash
# TEST-NAME: Edge case - test mode with local provision
# ====================
#
# WHAT THIS TESTS:
#   Tests that -t flag works correctly with a different provision method
#   (local) instead of container, verifying the fix works across different
#   provision backends.
#
# TEST COMMAND:
#   tmt run -ar provision -h local login -t -c true
#
# EXPECTED BEHAVIOR:
#   - With local provision and -t flag, login should occur after each test
#   - Login should occur in execute step (per-test behavior)
#   - Should NOT login again in finish step (this is the bug being fixed)
#   - The -t flag implicitly adds --step execute to prevent duplicate login
#   - Behavior should be identical to container provision
#
# KEY POINT:
#   This test verifies that the fix for Issue #1918 works across different
#   provision methods. While most tests use -h container for speed and
#   simplicity, it's important to verify the behavior is consistent with
#   other provisioners like local.
#
# TEST DATA:
#   - Creates 2 passing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section E-15

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 2
    rlPhaseEnd

    rlPhaseStartTest "Login -t with local provision"
        rlRun -s "tmt run -ar provision -h local login -t -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
