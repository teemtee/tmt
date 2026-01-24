#!/bin/bash
# B-11: Login --when pass --step execute
# Expected: Login in execute step only if test passes

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when pass --step execute"
        rlRun -s "tmt run -ar provision -h container login --when pass --step execute -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep interactive" 0 "Login in execute"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
