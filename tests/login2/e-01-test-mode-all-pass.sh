#!/bin/bash
# E-01: Login -t --when fail (all tests pass)
# ============================================
#
# WHAT THIS TESTS:
#   Edge case: Test mode with `--when fail` when all tests pass.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - Since NO tests fail, the condition is never met
#   - Should have 0 logins (login never occurs)
#   - This verifies that conditional login properly checks test results
#
# TEST DATA:
#   - 3 passing tests (test1, test2, test3)
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "E-01 to E-12: Edge Cases"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail (all pass)"
        rlRun -s "tmt run -ar provision -h container login -t --when fail -c true"
        login_count=$(grep -c "interactive" "$rlRun_LOG" || echo "0")
        rlAssertEquals "Should have 0 logins" "$login_count" "0"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
