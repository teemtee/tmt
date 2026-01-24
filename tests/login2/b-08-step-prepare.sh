#!/bin/bash
# TEST-NAME: Login with --step prepare option
# ====================
#
# WHAT THIS TESTS:
#   Tests that login occurs during the prepare step, before any tests execute.
#   This allows for early intervention or debugging during guest preparation.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --step prepare -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur during the prepare step
#   - Login should happen before any tests are executed
#   - The prepare step is enabled explicitly for this test
#
# KEY POINT:
#   This tests login during the prepare step, which occurs after provision
#   but before test execution. This is useful for debugging or setup verification.
#
# TEST DATA:
#   - Creates one normal test (prepare step is explicitly enabled)
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-08

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan true
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --step prepare"
        rlRun -s "tmt run -ar provision -h container login --step prepare -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    prepare$' -A20 '$rlRun_LOG' | grep -i interactive" 0 "Login in prepare"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
