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

        if ! rlIsFedora; then
            rlDie "Test requires Fedora"
        fi

        fedora_release=43
        build_container_image "fedora/${fedora_release}:latest"

        # Get koji build ID for make
        make_build_id=$(get_koji_build_id "make" "f${fedora_release}")
    rlPhaseEnd

    rlPhaseStartTest "Test multiple providers"
        rlRun "tmt run -i $run --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare --how artifact \
                --provide koji.build:$make_build_id \
                --provide repository-url:https://download.docker.com/linux/fedora/docker-ce.repo" 0 "Run with multiple providers"

        rlAssertGrep "make" "$run/log.txt"
        rlAssertGrep "docker-ce-cli" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
