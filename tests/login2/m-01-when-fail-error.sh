#!/bin/bash
# M-01: Login --when fail --when error
# =======================================
#
# WHAT THIS TESTS:
#   Multiple conditional filters (OR logic) without test mode.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when fail --when error -c true
#
# EXPECTED BEHAVIOR:
#   - Multiple `--when` conditions are OR'd together
#   - Login occurs if ANY condition matches
#   - Conditions are evaluated at end in finish step (not per-test)
#   - With pass + fail + error tests: login occurs (at least one condition met)
#
# KEY POINT:
#   `--when fail --when error` means: login if any test fails OR errors.
#
# TEST DATA:
#   - pass test: exits with 0
#   - fail test: exits with 1
#   - error test: exits with 99
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "M-01 to M-08: Multiple Conditions"

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
