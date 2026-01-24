#!/bin/bash
# B-08: Login --step prepare
# Expected: Login in prepare step

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan true
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --step prepare"
        rlRun -s "tmt run -ar provision -h container login --step prepare -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    prepare$' -A20 '$rlRun_LOG' | grep -i interactive" 0 "Login in prepare"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
