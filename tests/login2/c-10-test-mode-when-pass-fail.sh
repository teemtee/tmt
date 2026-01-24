#!/bin/bash
# C-10: Login -t --when pass --when fail
# Expected: Login after every test in execute (all pass or fail)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when pass --when fail"
        rlRun -s "tmt run -ar provision -h container login -t --when pass --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
