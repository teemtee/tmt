#!/bin/bash
# R-01: Result type - pass
# =========================
#
# WHAT THIS TESTS:
#   Login behavior with `--when pass` condition.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when pass -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step if ANY test passed
#   - With 2 pass + 1 fail tests: at least one test passed, so login occurs
#   - Login happens once in finish step (not per-test)
#
# TEST DATA:
#   - pass1 test: exits with 0
#   - pass2 test: exits with 0
#   - fail test: exits with 1
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "R-01 to R-05: Result Variations"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_two_pass_tests
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Result type - pass"
        rlRun -s "tmt run -ar provision -h container login --when pass -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
