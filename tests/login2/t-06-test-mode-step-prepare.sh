#!/bin/bash
# TEST-NAME: Test mode with --step prepare (override)
# ====================
#
# WHAT THIS TESTS:
#   Tests that explicit --step prepare overrides the implicit test mode
#   behavior, resulting in a single login during prepare step instead of
#   per-test login during execute.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step prepare -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur once during prepare step
#   - Login should NOT be per-test during execute
#   - The explicit --step prepare overrides the -t flag's default execute step
#
# KEY POINT:
#   Explicit --step specification should override the implicit --step execute
#   that -t normally provides. This tests that override behavior works correctly.
#
# TEST DATA:
#   - Creates two normal passing tests (prepare step is explicitly enabled)
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section T-06

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan true
        login2_create_test "test1" "true"
        login2_create_test "test2" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step prepare (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step prepare -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
