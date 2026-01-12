#!/bin/bash
# Example test for using multiple artifact providers together
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1
. ../../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "run2=\$(mktemp -d)" 0 "Create second run directory"

        if ! rlIsFedora; then
            rlDie "Test requires Fedora"
        fi

        fedora_release=43
        image_name="fedora/${fedora_release}:latest"
        build_container_image "$image_name"

        # Get koji build ID for make
        make_build_id=$(get_koji_build_id "make" "f${fedora_release}")
        if [ -z "$make_build_id" ]; then
            rlDie "Failed to get koji build ID for make"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Test multiple providers with command-line override"
        rlRun "tmt run -i $run --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --how artifact \
                --provide koji.build:$make_build_id \
                --provide repository-url:https://download.docker.com/linux/fedora/docker-ce.repo" 0 "Run with multiple providers"

        rlAssertGrep "make" "$run/log.txt"
        rlAssertGrep "docker-ce-cli" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartTest "Test multiple providers from plan file"
        rlRun "tmt run -i $run2 --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name" 0 "Run with multiple providers from plan file only"

        rlAssertGrep "make" "$run2/log.txt"
        rlAssertGrep "docker-ce-cli" "$run2/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run $run2"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
