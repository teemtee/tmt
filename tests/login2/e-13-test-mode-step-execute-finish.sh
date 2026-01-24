#!/bin/bash
# TEST-NAME: Edge case - test mode with both execute and finish steps
# ====================
#
# WHAT THIS TESTS:
#   Tests that when both execute and finish steps are explicitly specified
#   with -t flag, login occurs in BOTH steps (execute per-test AND finish).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step execute --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur after each test in execute step (per-test behavior)
#   - Login should ALSO occur once in finish step
#   - With 2 tests, should see 3 total logins (2 per-test + 1 in finish)
#   - Multiple `--step` options are additive
#
# KEY POINT:
#   This tests the edge case where BOTH execute and finish steps are explicitly
#   specified with -t flag. Multiple --step options combine to allow login in
#   multiple steps even with -t.
#
# TEST DATA:
#   - Creates 2 passing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section E-13

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 2
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step execute --step finish (both steps)"
        rlRun -s "tmt run -ar provision -h container login -t --step execute --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
