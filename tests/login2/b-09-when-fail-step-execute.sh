#!/bin/bash
# TEST-NAME: Login with --when fail --step execute
# ====================
#
# WHAT THIS TESTS:
#   Tests that conditional login (--when fail) works when combined with
#   explicit step specification (--step execute), triggering login in
#   the execute step only if tests fail.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when fail --step execute -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in the execute step (after all tests)
#   - Login should only trigger if at least one test fails
#   - Login should not occur in the finish step
#
# KEY POINT:
#   This tests combining conditional login (--when) with explicit step
#   specification, demonstrating that the condition is evaluated at the
#   end of the specified step.
#
# TEST DATA:
#   - Creates one passing test
#   - Creates one failing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section B-09

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --step execute"
        rlRun -s "tmt run -ar provision -h container login --when fail --step execute -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep interactive" 0 "Login in execute"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
