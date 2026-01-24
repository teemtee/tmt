#!/bin/bash
# TEST-NAME: Test mode with multiple --when conditions (fail and warn)
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) with multiple --when conditions (fail and warn)
#   results in per-test login during execute for tests matching ANY condition.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail --when warn -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur at least once in execute step
#   - Login occurs after each test that fails OR has warnings
#   - Passing tests should not trigger login
#   - Login should not occur in finish step
#
# KEY POINT:
#   In test mode, multiple --when conditions are OR'd together per-test.
#   Login occurs after each test that matches ANY condition (fail OR warn).
#
# TEST DATA:
#   - Creates one passing test
#   - Creates one failing test
#   - Creates one warning test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section M-05

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
        login2_create_warn_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --when warn"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlAssertGreaterOrEqual "Should have at least 1 login" "$(grep -c "interactive" "$rlRun_LOG")" "1"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
