#!/bin/bash
# TEST-NAME: Test mode with --when pass option
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) combined with conditional login (--when pass)
#   results in per-test login during execute step only for passing tests.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when pass -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur twice in execute step (after each passing test)
#   - Login should not occur after the failing test
#   - Login should not occur in finish step
#
# KEY POINT:
#   The -t flag means per-test login. Combined with --when pass, it should
#   login only after tests that pass. This verifies conditional filtering
#   works correctly in test mode.
#
# TEST DATA:
#   - Creates two passing tests
#   - Creates one failing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section T-04

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_two_pass_tests
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when pass"
        rlRun -s "tmt run -ar provision -h container login -t --when pass -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
