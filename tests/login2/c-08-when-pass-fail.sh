#!/bin/bash
# TEST-NAME: Multiple --when conditions (pass and fail)
# ====================
#
# WHAT THIS TESTS:
#   Tests that multiple --when conditions (pass and fail) are OR'd together,
#   triggering login in finish step if ANY test passes OR fails (which covers
#   all tests in this case).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when pass --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step
#   - Login should trigger since we have both passing and failing tests
#   - Multiple --when clauses are combined with OR logic
#
# KEY POINT:
#   Multiple --when conditions are OR'd together. Since pass and fail
#   cover most test outcomes, this typically results in login unless
#   all tests have other results (error, warn, info).
#
# TEST DATA:
#   - Creates one passing test
#   - Creates one failing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section C-08

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when pass --when fail"
        rlRun -s "tmt run -ar provision -h container login --when pass --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
