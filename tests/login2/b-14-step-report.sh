#!/bin/bash
# TEST-NAME: Login with --step report option
# ====================
#
# WHAT THIS TESTS:
#   Tests that login occurs during the report step, which happens after
#   finish and is used for generating and displaying test reports.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --step report -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur during the report step
#   - Login should happen after the finish step completes
#   - The report step must be enabled for this to work
#
# KEY POINT:
#   This tests login during the report step, which is the final step in
#   the workflow. Useful for debugging report generation or inspecting
#   the final state after all processing is complete.
#
# TEST DATA:
#   - Creates one normal passing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-14

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --step report"
        rlRun -s "tmt run -ar provision -h container login --step report -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    report$' -A5 '$rlRun_LOG' | grep -i interactive" 0 "Login in report"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
