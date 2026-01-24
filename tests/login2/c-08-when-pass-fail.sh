#!/bin/bash
# C-08: Login --when pass --when fail
# Expected: Login in finish (all tests are either pass or fail)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when pass --when fail"
        rlRun -s "tmt run -ar provision -h container login --when pass --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
