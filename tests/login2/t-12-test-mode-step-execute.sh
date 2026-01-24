#!/bin/bash
# TEST-NAME: Test mode with --step execute (redundant)
# ====================
#
# WHAT THIS TESTS:
#   Tests that explicitly specifying --step execute with -t flag is
#   redundant but should still work correctly, resulting in per-test login.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step execute -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur twice (once per test)
#   - The --step execute is redundant since -t already implies execute step
#   - Behavior should be identical to using -t alone
#
# KEY POINT:
#   The -t flag implicitly adds --step execute. Explicitly specifying it
#   should not change behavior - it's redundant but harmless.
#
# TEST DATA:
#   - Creates two normal passing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section T-12

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test1" "true"
        login2_create_test "test2" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step execute (redundant)"
        rlRun -s "tmt run -ar provision -h container login -t --step execute -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
