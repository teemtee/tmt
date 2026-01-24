#!/bin/bash
# B-09: Login --when fail --step execute
# Expected: Login in execute step only if test fails

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --step execute"
        rlRun -s "tmt run -ar provision -h container login --when fail --step execute -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep interactive" 0 "Login in execute"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
