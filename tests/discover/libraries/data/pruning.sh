#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlAssertRpm "coreutils"
        rlRun "rlImport database/mariadb"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "mariadbStart"
    rlPhaseEnd
rlJournalEnd
