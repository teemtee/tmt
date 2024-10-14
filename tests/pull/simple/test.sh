#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmt directory"
        rlRun "pushd $tmp"
    rlPhaseEnd

    rlPhaseStartTest "Test one step ($PROVISION_HOW)"
        rlRun "tmt run -i $run --scratch provision -h $PROVISION_HOW finish"
    rlPhaseEnd

    rlPhaseStartTest "Test two steps ($PROVISION_HOW)"
        rlRun "tmt run -i $run --scratch provision -h $PROVISION_HOW"
        rlRun "tmt run -i $run finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run $tmp" 0 "Remove run & tmp directory"
    rlPhaseEnd
rlJournalEnd
