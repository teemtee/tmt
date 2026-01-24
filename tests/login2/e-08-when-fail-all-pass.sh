#!/bin/bash
# TEST-NAME: Edge case - --when fail with all tests passing
# ====================
#
# WHAT THIS TESTS:
#   Tests the edge case of conditional login (--when fail) when all tests
#   pass, meaning the condition is never met and no login should occur.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - No login should occur (no tests fail)
#   - The condition --when fail is never satisfied
#   - This tests that conditional login properly handles no-match scenarios
#
# KEY POINT:
#   This tests that --when conditions properly handle cases where no tests
#   match the condition. When no tests fail, --when fail should not trigger login.
#
# TEST DATA:
#   - Creates 3 passing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section E-08

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail (all pass)"
        rlRun -s "tmt run -ar provision -h container login --when fail -c true"
        login_count=$(grep -c "interactive" "$rlRun_LOG" || echo "0")
        rlAssertEquals "Should have 0 logins" "$login_count" "0"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
