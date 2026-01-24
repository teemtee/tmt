#!/bin/bash
# E-08: Login --when fail (all tests pass)
# Expected: No login (condition never met)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail (all pass)"
        rlRun -s "tmt run -ar provision -h container login --when fail -c true"
        login_count=$(grep -c "interactive" "$rlRun_LOG" || echo "0")
        rlAssertEquals "Should have 0 logins" "$login_count" "0"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
