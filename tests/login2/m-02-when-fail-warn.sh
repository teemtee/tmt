#!/bin/bash
# M-02: Login --when fail --when warn
# Expected: Login in finish if any failed OR warned

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_fail_warn_tests
    rlPhaseEnd

    rlPhaseStartTest "Login --when fail --when warn"
        rlRun -s "tmt run -ar provision -h container login --when fail --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
