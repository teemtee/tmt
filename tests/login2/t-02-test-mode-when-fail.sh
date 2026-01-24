#!/bin/bash
# T-02: Login -t --when fail
# ===========================
#
# WHAT THIS TESTS:
#   Per-test login with conditional filter `--when fail` in test mode.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -t --when fail -c true
#
# EXPECTED BEHAVIOR:
#   - Login should occur ONLY after FAILING tests during execute step
#   - Should NOT login after passing tests
#   - Should NOT login in finish step
#   - With 1 pass + 1 fail test, should see exactly 1 login (after the fail)
#
# TEST DATA:
#   - pass test: exits with 0 (no login expected)
#   - fail test: exits with 1 (login expected after this test)
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "T-01 to T-12: Test Mode Scenarios"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Test mode with -t --when fail"
        rlRun -s "tmt run -ar provision -h container login -t --when fail -c true"
        login2_assert_login_count 1
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep interactive" 0 "Login in execute"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
