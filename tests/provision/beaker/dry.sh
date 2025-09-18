#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Verify that beaker-watchdog is set to panic=ignore by default"
        rlRun -s "tmt run --dry provision --how beaker --image Fedora-42 plan --default"
        rlAssertGrep 'watchdog panic="ignore"/' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify that beaker-watchdog is set to return the host to beaker when a kernel panic is detected"
        rlRun -s "tmt run --dry provision --how beaker --return-on-panic --image Fedora-42 plan --default"
        rlAssertNotGrep 'watchdog panic="ignore"/' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Verify beaker return-on-panic schema option works"
        rlRun -s "tmt run --dry plan --name /plan/watchdog"
        rlAssertNotGrep 'watchdog panic="ignore"/' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
