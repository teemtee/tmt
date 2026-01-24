#!/bin/bash
# TEST-NAME: Login with --when error option
# ====================
#
# WHAT THIS TESTS:
#   Tests that login occurs only when test results contain errors,
#   and the login happens in the finish step (default step behavior).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when error -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in the finish step
#   - Login should only trigger if at least one test has an error result
#   - No login should occur if no tests have errors
#
# KEY POINT:
#   This tests conditional login behavior with the error result type,
#   using the default step (finish) since no --step is specified.
#
# TEST DATA:
#   - Creates one normal passing test
#   - Creates one test that errors
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-03

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_normal_test
        login2_create_error_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when error"
        rlRun -s "tmt run -ar provision -h container login --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
