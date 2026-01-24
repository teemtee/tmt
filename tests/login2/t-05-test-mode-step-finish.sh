#!/bin/bash
# T-05: Login -t --step finish (override)
# Expected: Login in finish (user overrode -t default)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_tests 2
    rlPhaseEnd

    rlPhaseStartTest "Login -t --step finish (override)"
        rlRun -s "tmt run -ar provision -h container login -t --step finish -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 1
        login2_assert_login_in_step "finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
