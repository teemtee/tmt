#!/bin/bash
# E-07: Login --when fail with no tests discovered
# Expected: No login (no results to check)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan_no_tests
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail with no tests discovered"
        rlRun -s "tmt run -ar provision -h container login --when fail -c true" 0-2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
