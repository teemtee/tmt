#!/bin/bash
# Example test for koji.build artifact provider
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1
. ../../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        if ! rlIsFedora; then
            rlDie "Test requires Fedora"
        fi

        fedora_release=43
        build_container_image "fedora/${fedora_release}:latest"

        # Get koji build ID for make
        make_build_id=$(get_koji_build_id "make" "f${fedora_release}")
        if [ -z "$make_build_id" ]; then
            rlDie "Failed to get koji build ID for make"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Test koji.build provider"
        rlRun "tmt run -i $run --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare --how artifact --provide koji.build:$make_build_id" 0 "Run with koji.build provider"

        rlAssertGrep "tmt-artifact-shared" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
