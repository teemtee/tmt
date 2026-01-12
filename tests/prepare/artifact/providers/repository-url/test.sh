#!/bin/bash
# Example test for repository-url artifact provider
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1

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
    rlPhaseEnd

    rlPhaseStartTest "Test repository-url provider with command-line override"
        rlRun "tmt run -i $run --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --how artifact --provide repository-url:https://download.docker.com/linux/fedora/docker-ce.repo" 0 "Run with repository-url provider"

        rlAssertGrep "docker-ce-cli" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartTest "Test repository-url provider from plan file"
        rlRun "tmt run -i $run2 --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name" 0 "Run with repository-url provider from plan file only"

        rlAssertGrep "docker-ce-cli" "$run2/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run $run2"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
