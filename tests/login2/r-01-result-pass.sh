#!/bin/bash
# R-01: Result type - pass
# Demonstrates pass result type behavior

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_two_pass_tests
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Result type - pass"
        rlRun -s "tmt run -ar provision -h container login --when pass -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
