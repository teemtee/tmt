#!/bin/bash
# B-03: Login --when error
# Expected: Login in finish only if any test errored

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_normal_test
        login2_create_error_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when error"
        rlRun -s "tmt run -ar provision -h container login --when error -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
