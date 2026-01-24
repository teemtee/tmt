#!/bin/bash
# TEST-NAME: Test mode with multiple --when and explicit --step finish
# ====================
#
# WHAT THIS TESTS:
#   Tests the complex combination of test mode (-t), multiple --when conditions
#   (fail and error), and explicit step specification (--step finish), resulting
#   in per-test login in execute AND additional login in finish.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail --when error --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur at least twice total
#   - Once or more in execute step (after each fail/error test)
#   - Once in finish step (due to explicit --step finish)
#
# KEY POINT:
#   This tests a complex scenario where -t with multiple --when conditions
#   provides per-test login for failures/errors in execute, AND explicit
#   --step finish adds an additional login in finish. Both behaviors coexist.
#
# TEST DATA:
#   - Creates tests with pass, fail, and error results
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section M-08

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_fail_error_tests
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --when error --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --when error --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlAssertGreaterOrEqual "Should have at least 2 logins" "$(grep -c "interactive" "$rlRun_LOG")" "2"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
