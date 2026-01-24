#!/bin/bash
# C-06: Login -t --step prepare --step finish
# Expected: Login in prepare + finish (not per-test)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan true
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step prepare --step finish"
        rlRun -s "tmt run -ar provision -h container login -t --step prepare --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
