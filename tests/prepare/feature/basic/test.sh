#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        build_container_image "fedora/latest/upstream\:latest"

        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test whether unserialization works"
        rlRun "tmt -vv run --id $run --scratch --until prepare"
        rlRun "tmt -vv run --id $run prepare"
        rlRun "tmt -vv run --id $run finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Removing run directory"
    rlPhaseEnd
rlJournalEnd
