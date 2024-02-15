#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test ($PROVISION_HOW)"
        rlRun "tmt run -arvvv provision --how $PROVISION_HOW"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
