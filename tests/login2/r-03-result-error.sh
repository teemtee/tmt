#!/bin/bash
# R-03: Result type - error
# Demonstrates error result type behavior (infrastructure issue)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_normal_test
        login2_create_two_error_tests
    rlPhaseEnd

    rlPhaseStartTest "Result type - error"
        rlRun -s "tmt run -ar provision -h container login --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
