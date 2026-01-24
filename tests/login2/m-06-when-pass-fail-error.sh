#!/bin/bash
# TEST-NAME: Multiple --when conditions (pass, fail, and error)
# ====================
#
# WHAT THIS TESTS:
#   Tests that multiple --when conditions (pass, fail, and error) are OR'd
#   together, triggering login in finish step if ANY test passes, fails, or errors.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when pass --when fail --when error -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step
#   - Login should trigger since we have pass, fail, and error results
#   - Multiple --when clauses are combined with OR logic
#
# KEY POINT:
#   Multiple --when conditions are OR'd together. This tests combining
#   three conditions (pass, fail, error) which covers most test outcomes.
#
# TEST DATA:
#   - Creates tests with pass, fail, and error results
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section M-06

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_fail_error_tests
    rlPhaseEnd

    rlPhaseStartTest "Login --when pass --when fail --when error"
        rlRun -s "tmt run -ar provision -h container login --when pass --when fail --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
