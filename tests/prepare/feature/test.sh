#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        build_container_image "centos/stream9/upstream\:latest"
        build_container_image "ubi/8/upstream\:latest"

        rlRun "pushd data"
    rlPhaseEnd

    images="$TEST_IMAGE_PREFIX/centos/stream9/upstream:latest $TEST_IMAGE_PREFIX/ubi/8/upstream:latest ubi9"

    # EPEL
    for image in $images; do
        rlPhaseStartTest "Enable EPEL on $image"
            rlRun -s "tmt -vvv run -a plan --name '/epel/enabled' provision --how container --image $image"
        rlPhaseEnd

        rlPhaseStartTest "Disable EPEL on $image"
            rlRun -s "tmt -vvv run -a plan --name '/epel/disabled' provision --how container --image $image"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
