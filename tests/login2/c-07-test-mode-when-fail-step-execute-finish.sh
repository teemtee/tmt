#!/bin/bash
# TEST-NAME: Test mode with --when fail and multiple steps
# ====================
#
# WHAT THIS TESTS:
#   Tests the complex combination of test mode (-t), conditional login
#   (--when fail), and multiple step specifications (--step execute and
#   --step finish), resulting in per-test login AND finish step login.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail --step execute --step finish -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur twice total
#   - Once in execute step (after the failing test)
#   - Once in finish step (due to explicit --step finish)
#
# KEY POINT:
#   This tests a complex scenario where -t with --when fail provides
#   per-test login for failures in execute, AND explicit --step finish
#   adds an additional login in finish. Both behaviors coexist.
#
# TEST DATA:
#   - Creates one passing test
#   - Creates one failing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section C-07

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --step execute --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --step execute --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
