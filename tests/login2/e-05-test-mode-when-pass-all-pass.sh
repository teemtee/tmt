#!/bin/bash
# TEST-NAME: Edge case - test mode with all tests passing
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) with --when pass results in per-test login
#   after every test when ALL tests pass (all meet the condition).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when pass -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur three times in execute step (after each passing test)
#   - Every test triggers login since all pass
#   - Login should not occur in finish step
#
# KEY POINT:
#   This tests the edge case where all tests match the --when pass condition,
#   demonstrating that login occurs after each test when all conditions are met.
#
# TEST DATA:
#   - Creates 3 passing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section E-05

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when pass (all pass)"
        rlRun -s "tmt run -ar provision -h container login -t --when pass -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
