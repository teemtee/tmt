#!/bin/bash
# TEST-NAME: Login with --step provision option (error case)
# ====================
#
# WHAT THIS TESTS:
#   Tests that attempting to login during the provision step results in an error
#   because guests are not fully ready/available at that point in the workflow.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --step provision -c true
#
# EXPECTED BEHAVIOR:
#   - The command should fail with exit code 1 or 2
#   - Error message should indicate "No guests ready for login"
#   - This is expected behavior since provision is still in progress
#
# KEY POINT:
#   This tests the step availability constraint - login cannot occur during
#   provision because guests are not ready. This documents the error handling.
#
# TEST DATA:
#   - Creates one normal test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-13

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --step provision"
        rlRun -s "tmt run -ar provision -h container login --step provision -c true" 0-2
        rlAssertGrep "No guests ready for login" "$rlRun_LOG" 0 "No guests in provision"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
