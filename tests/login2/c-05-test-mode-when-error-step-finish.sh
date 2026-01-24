#!/bin/bash
# C-05: Login -t --when error --step finish
# Expected: Login after each errored test (execute) + in finish

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
