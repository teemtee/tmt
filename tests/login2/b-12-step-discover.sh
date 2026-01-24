#!/bin/bash
# B-12: Login --step discover
# Expected: No guests ready for login in discover

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --step discover"
        rlRun -s "tmt run -ar provision -h container login --step discover -c true" 0-2
        rlAssertGrep "No guests ready for login" "$rlRun_LOG" 0 "No guests in discover"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
