#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

export TMT_SSH_MASTER_START_TIMEOUT=10

rlJournalStart
    rlPhaseStartSetup
        rlRun "export TMT_NO_COLOR=1"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Login into the guest"
        rlRun -s "./login.exp" 0 "Try to log into the guest"
        rlAssertGrep "login: Starting interactive shell" "$rlRun_LOG"
        rlAssertNotGrep "_wait_for_ssh_master' timed out" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
