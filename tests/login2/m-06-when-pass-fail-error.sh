#!/bin/bash
# M-06: Login --when pass --when fail --when error
# Expected: Login in finish (covers all result types)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_fail_error_tests
    rlPhaseEnd

    rlPhaseStartTest "Login --when pass --when fail --when error"
        rlRun -s "tmt run -ar provision -h container login --when pass --when fail --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
