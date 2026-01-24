#!/bin/bash
# TEST-NAME: Login with --when pass option
# ====================
#
# WHAT THIS TESTS:
#   Tests that login occurs only when all test results are pass,
#   and the login happens in the finish step (default step behavior).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when pass -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in the finish step
#   - Login should only trigger if at least one test passes
#   - No login should occur if no tests pass
#
# KEY POINT:
#   This tests conditional login behavior with the pass result type,
#   using the default step (finish) since no --step is specified.
#
# TEST DATA:
#   - Creates two tests that both pass
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-04

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test1" "true"
        login2_create_test "test2" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --when pass"
        rlRun -s "tmt run -ar provision -h container login --when pass -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
