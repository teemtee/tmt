#!/bin/bash
# M-03: Login -t --when fail --when error
# ==========================================
#
# WHAT THIS TESTS:
#   Multiple conditional filters (OR logic) WITH test mode.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail --when error -c true
#
# EXPECTED BEHAVIOR:
#   - Multiple `--when` conditions are OR'd together
#   - With `-t`, conditions are evaluated PER-TEST during execute
#   - Login occurs after EACH test that meets ANY condition
#   - With pass + fail + error: login after fail and error tests only
#
# KEY POINT:
#   In test mode with multiple conditions, each test is evaluated
#   independently - login occurs after each matching test.
#
# TEST DATA:
#   - pass test: no condition match (no login)
#   - fail test: matches --when fail (login occurs)
#   - error test: matches --when error (login occurs)
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

    rlPhaseStartTest "Login -t --when fail --when error"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlAssertGreaterOrEqual "Should have at least 1 login" "$(grep -c "interactive" "$rlRun_LOG")" "1"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
