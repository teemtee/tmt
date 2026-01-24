#!/bin/bash
# M-05: Login -t --when fail --when warn
# Expected: Login after each failed or warned test in execute

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
        login2_create_warn_test
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --when warn"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlAssertGreaterOrEqual "Should have at least 1 login" "$(grep -c "interactive" "$rlRun_LOG")" "1"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
