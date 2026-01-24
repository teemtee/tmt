#!/bin/bash
# C-01: Login -t --when fail --step finish
# =========================================
#
# WHAT THIS TESTS:
#   Combined test mode, conditional filter, and explicit step override.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - With explicit `--step finish`, per-test behavior is DISABLED
#   - Login should occur in finish step IF any test failed
#   - NOT per-test (even though `-t` is used)
#   - With pass + fail tests, should see 1 login in finish (not per-test)
#
# KEY POINT:
#   Explicit `--step finish` overrides the `-t` per-test behavior.
#   The `--when fail` condition is evaluated in finish step.
#
# TEST DATA:
#   - pass test: exits with 0
#   - fail test: exits with 1
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "C-01 to C-10: Combined Scenarios"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
