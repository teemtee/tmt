#!/bin/bash
# B-15: Login --when info
# Expected: Login in finish if test has info messages

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ./common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        login2_setup
        login2_create_plan
        login2_create_info_test
    rlPhaseEnd

    rlPhaseStartTest "Login --when info"
        rlRun -s "tmt run -ar provision -h container login --when info -c true"
        rlAssertGrep "interactive" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        login2_cleanup
    rlPhaseEnd
rlJournalEnd
