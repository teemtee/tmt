#!/bin/bash
# TEST-NAME: Edge case - test mode with --step report (override)
# ====================
#
# WHAT THIS TESTS:
#   Tests that explicit --step report overrides the implicit test mode
#   behavior, resulting in a single login during report step instead of
#   per-test login during execute.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step report -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur once during report step
#   - Login should NOT be per-test during execute
#   - The explicit --step report overrides the -t flag's default execute step
#
# KEY POINT:
#   Explicit --step specification should override the implicit --step execute
#   that -t normally provides. This tests that override behavior works for
#   the report step.
#
# TEST DATA:
#   - Creates two normal passing tests (report step must be enabled)
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section E-11

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan_with_report
        login2_create_test "test1" "true"
        login2_create_test "test2" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step report (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step report -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
