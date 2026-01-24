#!/bin/bash
# TEST-NAME: Login with --when info option
# ====================
#
# WHAT THIS TESTS:
#   Tests that login occurs only when test results contain info messages,
#   and the login happens in the finish step (default step behavior).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when info -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in the finish step
#   - Login should only trigger if at least one test has info messages
#   - No login should occur if no tests have info messages
#
# KEY POINT:
#   This tests conditional login behavior with the info result type,
#   which captures tests that produce informational messages (typically
#   messages written to stderr with "info:" prefix).
#
# TEST DATA:
#   - Creates one test with info messages
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-15

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_info_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when info"
        rlRun -s "tmt run -ar provision -h container login --when info -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
