#!/bin/bash
# Example test for repository-url artifact provider
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        if ! rlIsFedora; then
            rlDie "Test requires Fedora"
        fi

        fedora_release=43
        image_name="fedora/${fedora_release}:latest"
        build_container_image "$image_name"
    rlPhaseEnd

    rlPhaseStartTest "Test repository-url provider"
        rlRun "tmt run -i $run --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name" 0 "Run with repository-url provider"

        rlAssertGrep "docker-ce-cli" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
