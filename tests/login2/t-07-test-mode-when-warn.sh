#!/bin/bash
# TEST-NAME: Test mode with --when warn option
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) combined with conditional login (--when warn)
#   results in per-test login during execute step only for tests with warnings.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when warn -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur twice in execute step (after each warned test)
#   - Login should not occur after the normal test
#   - Login should not occur in finish step
#
# KEY POINT:
#   The -t flag means per-test login. Combined with --when warn, it should
#   login only after tests that have warnings. This verifies conditional
#   filtering works correctly for warn results.
#
# TEST DATA:
#   - Creates two tests with warnings
#   - Creates one normal passing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section T-07

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_two_warn_tests
        login2_create_test "normal" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when warn"
        rlRun -s "tmt run -ar provision -h container login -t --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
