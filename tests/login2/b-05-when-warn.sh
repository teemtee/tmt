#!/bin/bash
# B-05: Login --when warn
# Expected: Login in finish only if any test has warnings

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_warn_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when warn"
        rlRun -s "tmt run -ar provision -h container login --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
