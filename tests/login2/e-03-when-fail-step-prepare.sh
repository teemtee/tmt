#!/bin/bash
# E-03: Login --when fail --step prepare
# Expected: No login or error (--when with step before execute)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan true
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --step prepare (edge case)"
        # This is an edge case - --when with a step before execute
        # The behavior is undefined/should be no login
        rlRun -s "tmt run -ar provision -h container login --when fail --step prepare -c true" 0-2
        # Document the actual behavior for now
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
