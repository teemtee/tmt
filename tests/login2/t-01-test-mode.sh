#!/bin/bash
# T-01: Login -t (test mode)
# Expected: Login after each test, NOT in finish

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Test mode login -t"
        rlRun -s "tmt run -ar provision -h container login -t -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
        rlRun "grep '^    execute$' -A20 '$rlRun_LOG' | grep -c interactive" 0 "Logins in execute"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
