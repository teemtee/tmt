#!/bin/bash
# T-05: Login -t --step finish (override)
# ========================================
#
# WHAT THIS TESTS:
#   Test mode with explicit `--step finish` option override.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - When explicit `--step finish` is given with `-t`, it overrides the
#     implicit `--step execute` behavior
#   - Login should occur ONCE in finish step (not per-test)
#   - This is the EXCEPTION to the rule - user explicitly wants finish step
#   - With 2 tests, should see exactly 1 login (in finish, not per-test)
#
# KEY POINT:
#   Explicit `--step` ALWAYS overrides the implicit `-t` behavior.
#   This allows intentional finish-step login when desired.
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

    rlPhaseStartTest "Login -t --step finish (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
