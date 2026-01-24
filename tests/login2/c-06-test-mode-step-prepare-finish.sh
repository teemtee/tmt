#!/bin/bash
# TEST-NAME: Test mode with multiple step specifications
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) with multiple explicit step specifications
#   (--step prepare and --step finish) results in login at ALL steps
#   including per-test in execute (additive behavior).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step prepare --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur three times total
#   - Once during prepare step (before tests run)
#   - Once after test in execute step (per-test behavior from -t)
#   - Once during finish step (after tests complete)
#
# KEY POINT:
#   Multiple explicit --step specifications are ADDITIVE with -t's per-test
#   behavior. -t always gives per-test login in execute, and --step adds
#   additional login points at other steps.
#
# TEST DATA:
#   - Creates one normal passing test (prepare step is explicitly enabled)
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section C-06

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan true
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step prepare --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --step prepare --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
