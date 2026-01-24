#!/bin/bash
# E-06: Login -t with no tests discovered
# =========================================
#
# WHAT THIS TESTS:
#   Edge case: Test mode when no tests are discovered.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t -c true
#
# EXPECTED BEHAVIOR:
#   - When no tests are discovered, there are no tests to trigger login
#   - Should have 0 logins (no tests = no per-test login opportunities)
#   - The discover filter points to a non-existent path
#
# KEY POINT:
#   Per-test login only occurs when there are tests. No tests = no login.
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "E-01 to E-12: Edge Cases"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan_no_tests
    rlPhaseEnd

    rlPhaseStartTest "Login -t with no tests discovered"
        rlRun -s "tmt run -ar provision -h container login -t -c true" 0-2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
