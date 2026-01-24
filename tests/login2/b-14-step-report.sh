#!/bin/bash
# B-14: Login --step report
# Expected: Login during report step

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_test "test" "true"
    rlPhaseEnd

    rlPhaseStartTest "Login --step report"
        rlRun -s "tmt run -ar provision -h container login --step report -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    report$' -A5 '$rlRun_LOG' | grep -i interactive" 0 "Login in report"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
