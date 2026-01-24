#!/bin/bash
# B-01: Default login (no options)
# =====================================
#
# WHAT THIS TESTS:
#   Default behavior of `tmt login` without any options.
#
# TEST COMMAND:
#   tmt run -ar provision -h container login -c true
#
# EXPECTED BEHAVIOR:
#   - Without any options, `tmt login` should default to logging in at the end
#     of the finish step (the last enabled step)
#   - The `-c true` option runs `true` instead of an interactive shell
#     (for automated testing)
#   - Should see exactly 1 login in the finish step
#
# SEE ALSO:
#   TEST_SUMMARY.md - Section "B-01 to B-15: Base Scenarios"

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test" "echo \"test1\"; true" "test: echo \"test1\"; true"
    rlPhaseEnd

    rlPhaseStartTest "Default login"
        rlRun -s "tmt run -ar provision -h container login -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
