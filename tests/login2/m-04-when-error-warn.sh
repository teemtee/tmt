#!/bin/bash
# TEST-NAME: Multiple --when conditions (error and warn)
# ====================
#
# WHAT THIS TESTS:
#   Tests that multiple --when conditions (error and warn) are OR'd together,
#   triggering login in finish step if ANY test errors OR has warnings.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when error --when warn -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step
#   - Login should trigger if any test errors OR has warnings
#   - Multiple --when clauses are combined with OR logic
#
# KEY POINT:
#   Multiple --when conditions are OR'd together - login occurs if ANY
#   condition is met. This tests combining error and warn conditions.
#
# TEST DATA:
#   - Creates tests with error and warn results
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section M-04

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_error_warn_tests
    rlPhaseEnd

    rlPhaseStartTest "Login --when error --when warn"
        rlRun -s "tmt run -ar provision -h container login --when error --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
