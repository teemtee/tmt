#!/bin/bash
# E-06: Login -t with no tests discovered
# Expected: No login (no tests = no logins)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan_no_tests
    rlPhaseEnd

    rlPhaseStartTest "Login -t with no tests discovered"
        rlRun -s "tmt run -ar provision -h container login -t -c true" 0-2
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
