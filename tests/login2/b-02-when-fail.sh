#!/bin/bash
# B-02: Login --when fail
# ===========================
#
# WHAT THIS TESTS:
#   Conditional login using `--when fail` option.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur ONLY if at least one test fails
#   - Login happens in the finish step (default step when --step not specified)
#   - Since this test includes a failing test, login should occur
#
# TEST DATA:
#   - pass test: exits with 0 (pass)
#   - fail test: exits with 1 (fail)
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "B-01 to B-15: Base Scenarios"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail"
        rlRun -s "tmt run -ar provision -h container login --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
