#!/bin/bash
# C-09: Login --when fail --step finish
# Expected: Login in finish if any failed (explicit finish)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_pass_test
        login2_create_fail_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --step finish"
        rlRun -s "tmt run -ar provision -h container login --when fail --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
