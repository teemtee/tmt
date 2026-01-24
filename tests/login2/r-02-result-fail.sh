#!/bin/bash
# R-02: Result type - fail
# Demonstrates fail result type behavior

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_two_fail_tests
    rlPhaseEnd

    rlPhaseStartTest "Result type - fail"
        rlRun -s "tmt run -ar provision -h container login --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
