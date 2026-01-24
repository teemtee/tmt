#!/bin/bash
# E-01: Login -t --when fail with all tests passing
# Expected: No login (condition never met)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail (all pass)"
        rlRun -s "tmt run -ar provision -h container login -t --when fail -c true"
        login_count=$(grep -c "interactive" "$rlRun_LOG" || echo "0")
        rlAssertEquals "Should have 0 logins" "$login_count" "0"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
