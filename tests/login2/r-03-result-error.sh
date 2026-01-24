#!/bin/bash
# R-03: Result type - error
# ==========================
#
# WHAT THIS TESTS:
#   Login behavior with `--when error` condition.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when error -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step if ANY test had an error
#   - Error = exit code 99 (infrastructure issue, distinct from test failure)
#   - With 1 normal + 2 error tests: at least one error, so login occurs
#
# TEST DATA:
#   - normal test: exits with 0 (pass)
#   - error1 test: exits with 99 (error)
#   - error2 test: exits with 99 (error)
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "R-01 to R-05: Result Variations"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_normal_test
        login2_create_two_error_tests
    rlPhaseEnd

    rlPhaseStartTest "Result type - error"
        rlRun -s "tmt run -ar provision -h container login --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
