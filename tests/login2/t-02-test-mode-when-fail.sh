#!/bin/bash
# T-02: Login -t --when fail
# Expected: Login only after failed tests, NOT in finish

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
