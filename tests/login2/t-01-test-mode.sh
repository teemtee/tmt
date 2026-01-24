#!/bin/bash
# T-01: Login -t (test mode)
# ============================
#
# WHAT THIS TESTS:
#   Per-test login behavior using the `-t` flag (test mode).
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t -c true
#
# EXPECTED BEHAVIOR (AFTER FIX):
#   - With `-t` flag, login should occur AFTER EACH TEST during execute step
#   - Should NOT login again in finish step (this is the bug being fixed)
#   - With 3 tests, should see exactly 3 logins (one per test)
#   - The `-t` flag implicitly adds `--step execute` to prevent duplicate login
#
# THE BUG (BEFORE FIX):
#   - Login occurred in BOTH execute (after each test) AND finish steps
#   - Result: 4 logins instead of 3 (3 per-test + 1 in finish)
#
# TEST DATA:
#   - 3 passing tests (test1, test2, test3)
#
# SEE ALSO:
#   GitHub Issue #1918 - https://github.com/teemtee/tmt/issues/1918
#   TEST_SUMMARY.md - Section "T-01 to T-12: Test Mode Scenarios"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Test mode login -t"
        rlRun -s "tmt run -ar provision -h container login -t -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep -c interactive" 0 "Logins in execute"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
