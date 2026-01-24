#!/bin/bash
# B-01: Default login (no options)
# Expected: Login at end of finish step

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
