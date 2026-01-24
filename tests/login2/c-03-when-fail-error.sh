#!/bin/bash
# TEST-NAME: Multiple --when conditions (fail and error)
# ====================
#
# WHAT THIS TESTS:
#   Tests that multiple --when conditions are OR'd together, triggering
#   login in finish step if ANY of the conditions match (fail OR error).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when fail --when error -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step
#   - Login should trigger if any test fails OR errors
#   - Multiple --when clauses are combined with OR logic
#
# KEY POINT:
#   Multiple --when conditions are OR'd together - login occurs if ANY
#   condition is met. This is different from requiring all conditions.
#
# TEST DATA:
#   - Creates tests with pass, fail, and error results
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section C-03

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_fail_error_tests
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --when error"
        rlRun -s "tmt run -ar provision -h container login --when fail --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
