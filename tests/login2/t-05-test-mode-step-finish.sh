#!/bin/bash
# T-05: Login -t --step finish (additive)
# ========================================
#
# WHAT THIS TESTS:
#   Test mode with explicit `--step finish` option - additive behavior.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - `-t` provides per-test login during execute step
#   - `--step finish` adds an additional login in finish step
#   - Both behaviors COMBINE (additive)
#   - With 2 tests, should see exactly 3 logins (2 per-test + 1 at finish)
#
# KEY POINT:
#   `-t` always means per-test login in execute.
#   Explicit `--step` adds additional login points.
#   This allows both per-test debugging AND final inspection.
#
# TEST DATA:
#   - 2 passing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "T-01 to T-12: Test Mode Scenarios"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 2
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step finish (additive)"
        rlRun -s "tmt run -ar provision -h container login -t --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
        # Verify logins in both execute and finish steps
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep -c interactive" 0 "Logins in execute"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
