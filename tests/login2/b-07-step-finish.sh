#!/bin/bash
# TEST-NAME: Login with --step finish option (explicit)
# ====================
#
# WHAT THIS TESTS:
#   Tests that login occurs during the finish step when explicitly specified.
#   This is the default step behavior, but here it's explicitly requested.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in the finish step
#   - Login should happen after all tests have completed
#   - This is the same as the default behavior, just explicitly specified
#
# KEY POINT:
#   This tests explicit specification of the finish step, which is also
#   the default step when no --step option is provided.
#
# TEST DATA:
#   - Creates one normal passing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-07

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --step finish"
        rlRun -s "tmt run -ar provision -h container login --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
