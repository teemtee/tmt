#!/bin/bash
# TEST-NAME: Test mode with multiple step specifications
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) with multiple explicit step specifications
#   (--step prepare and --step finish) results in login at both specified
#   steps, not per-test in execute.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step prepare --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur twice total
#   - Once during prepare step (before tests run)
#   - Once during finish step (after tests complete)
#   - No per-test login in execute (explicit steps override -t's default)
#
# KEY POINT:
#   Multiple explicit --step specifications can be provided. When specified,
#   they override the implicit --step execute from -t, resulting in login
#   at each specified step instead of per-test behavior.
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
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
