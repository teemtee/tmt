#!/bin/bash
# TEST-NAME: Login with --step discover option (error case)
# ====================
#
# WHAT THIS TESTS:
#   Tests that attempting to login during the discover step results in an error
#   because no guests have been provisioned yet at that point in the workflow.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --step discover -c true
#
# EXPECTED BEHAVIOR:
#   - The command should fail with exit code 1 or 2
#   - Error message should indicate "No guests ready for login"
#   - This is expected behavior since discover happens before provision
#
# KEY POINT:
#   This tests the step availability constraint - login cannot occur during
#   discover because guests don't exist yet. This documents the error handling.
#
# TEST DATA:
#   - Creates one normal test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-12

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --step discover"
        rlRun -s "tmt run -ar provision -h container login --step discover -c true" 0-2
        rlAssertGrep "No guests ready for login" "$rlRun_LOG" 0 "No guests in discover"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
