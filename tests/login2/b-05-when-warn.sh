#!/bin/bash
# TEST-NAME: Login with --when warn option
# ====================
#
# WHAT THIS TESTS:
#   Tests that login occurs only when test results contain warnings,
#   and the login happens in the finish step (default step behavior).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when warn -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in the finish step
#   - Login should only trigger if at least one test has a warning result
#   - No login should occur if no tests have warnings
#
# KEY POINT:
#   This tests conditional login behavior with the warn result type,
#   using the default step (finish) since no --step is specified.
#
# TEST DATA:
#   - Creates one test with a warning result
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-05

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_warn_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when warn"
        rlRun -s "tmt run -ar provision -h container login --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
