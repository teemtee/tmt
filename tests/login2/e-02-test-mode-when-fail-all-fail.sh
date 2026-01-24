#!/bin/bash
# E-02: Login -t --when fail with all tests failing
# Expected: Login after every test (all meet condition)

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_fail_tests 3
    rlPhaseEnd

    rlPhaseStartTest "Login -t --when fail (all fail)"
        rlRun -s "tmt run -ar provision -h container login -t --when fail -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
        login2_assert_login_count 3
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
