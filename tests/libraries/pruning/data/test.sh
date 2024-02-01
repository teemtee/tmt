#!/bin/bash
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
