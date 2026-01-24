#!/bin/bash
# C-02: Login -t --step execute --step finish
# ===========================================
#
# WHAT THIS TESTS:
#   Combined test mode with multiple explicit steps.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --step execute --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - `--step execute --step finish` means login in BOTH steps
#   - In execute step: per-test login (because of `-t`)
#   - In finish step: single login at end
#   - With 2 tests: should see 3 logins total (2 per-test + 1 in finish)
#
# KEY POINT:
#   Multiple `--step` options are additive - login occurs in each specified step.
#
# TEST DATA:
#   - 2 passing tests
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "C-01 to C-10: Combined Scenarios"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test1" "true"
        login2_create_test "test2" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step execute --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --step execute --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
