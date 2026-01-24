#!/bin/bash
# M-04: Login --when error --when warn
# Expected: Login in finish if any errored OR warned

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_error_warn_tests
    rlPhaseEnd

    rlPhaseStartTest "Login --when error --when warn"
        rlRun -s "tmt run -ar provision -h container login --when error --when warn -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
