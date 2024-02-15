#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
    rlPhaseEnd

    rlPhaseStartTest "Simple ($PROVISION_HOW)"
        rlRun "pushd data/simple"
        rlRun "tmt run -ar provision -h $PROVISION_HOW report -vvv"
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "Prepare ($PROVISION_HOW)"
        rlRun "pushd data/prepare"
        rlRun "tmt run -ar provision -h $PROVISION_HOW report -vvv"
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "Ansible ($PROVISION_HOW)"
        rlRun "pushd data/ansible"
        rlRun "tmt run -ar provision -h $PROVISION_HOW report -vvv"
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest "Verify the TMT_TREE variable ($PROVISION_HOW)"
        rlRun "pushd data/tree"
        rlRun "tmt run -ar provision -h $PROVISION_HOW report -vvv"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
