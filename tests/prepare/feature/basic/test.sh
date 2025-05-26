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
        rlRun "TMT_SHOW_TRACEBACK=full tmt -vv run --id $run --scratch --until prepare"
        rlRun "TMT_SHOW_TRACEBACK=full tmt -vv run --id $run prepare"
        rlRun "TMT_SHOW_TRACEBACK=full tmt -vv run --id $run finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Removing run directory"
    rlPhaseEnd
rlJournalEnd
