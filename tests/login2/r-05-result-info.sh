#!/bin/bash
# R-05: Result type - info
# Demonstrates info result type behavior

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_normal_test
        # Create two info tests
        login2_create_test "info1" "echo \"info: This is an info message\" >&2; true" "test: echo \"info: message\"; true"
        login2_create_test "info2" "echo \"info: More info\" >&2; true" "test: echo \"info: message2\"; true"
    rlPhaseEnd

    rlPhaseStartTest "Result type - info"
        rlRun -s "tmt run -ar provision -h container login --when info -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
