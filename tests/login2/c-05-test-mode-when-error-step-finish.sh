#!/bin/bash
# TEST-NAME: Test mode with --when error and explicit --step finish
# ====================
#
# WHAT THIS TESTS:
#   Tests the combination of test mode (-t), conditional login (--when error),
#   and explicit step specification (--step finish), resulting in login in
#   both execute (per errored test) AND finish steps.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when error --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur twice total
#   - Once in execute step (after the errored test)
#   - Once in finish step (due to explicit --step finish)
#
# KEY POINT:
#   When -t is combined with explicit --step finish, both behaviors apply:
#   per-test login in execute (for errors) AND single login in finish.
#   This tests that both step specifications can coexist.
#
# TEST DATA:
#   - Creates one normal passing test
#   - Creates one test that errors
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section C-05

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_normal_test
        login2_create_error_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when error --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --when error --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
