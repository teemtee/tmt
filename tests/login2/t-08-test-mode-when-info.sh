#!/bin/bash
# TEST-NAME: Test mode with --when info option
# ====================
#
# WHAT THIS TESTS:
#   Tests that test mode (-t) combined with conditional login (--when info)
#   results in per-test login during execute step only for tests with info messages.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when info -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur once in execute step (after the info test)
#   - Login should not occur after the normal test
#   - Login should not occur in finish step
#
# KEY POINT:
#   The -t flag means per-test login. Combined with --when info, it should
#   login only after tests that produce info messages. This verifies conditional
#   filtering works correctly for info results.
#
# TEST DATA:
#   - Creates one test with info messages
#   - Creates one normal passing test
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section T-08

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_info_test
        login2_create_test "normal" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when info"
        rlRun -s "tmt run -ar provision -h container login -t --when info -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
