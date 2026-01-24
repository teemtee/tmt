#!/bin/bash
# M-03: Login -t --when fail --when error
# Expected: Login after each failed or errored test in execute

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_fail_error_tests
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail --when error"
        rlRun -s "tmt run -ar provision -h container login -t --when fail --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        rlAssertGreaterOrEqual "Should have at least 1 login" "$(grep -c "interactive" "$rlRun_LOG")" "1"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
