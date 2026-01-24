#!/bin/bash
# TEST-NAME: Conditional login with explicit --step finish
# ====================
#
# WHAT THIS TESTS:
#   Tests that conditional login (--when fail) combined with explicit
#   step specification (--step finish) results in login in finish step
#   only if tests fail.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login --when fail --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur in finish step
#   - Login should only trigger if at least one test fails
#   - The explicit --step finish is redundant (finish is the default)
#
# KEY POINT:
#   This tests the combination of --when with explicit --step finish.
#   While finish is the default step, explicitly specifying it makes
#   the intent clear and should work identically.
#
# TEST DATA:
#   - Creates one passing test
#   - Creates one failing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section C-09

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --step finish"
        rlRun -s "tmt run -ar provision -h container login --when fail --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
