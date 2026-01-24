#!/bin/bash
# B-13: Login --step provision
# Expected: No guests ready for login in provision

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --step provision"
        rlRun -s "tmt run -ar provision -h container login --step provision -c true" 0-2
        rlAssertGrep "No guests ready for login" "$rlRun_LOG" 0 "No guests in provision"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
