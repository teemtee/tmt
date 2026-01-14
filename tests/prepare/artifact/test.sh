#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1
. lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        setup_fedora_environment

        # Get koji build ID for make using common function
        get_koji_build_id "make" "f${fedora_release}"
        make_build_id="$KOJI_BUILD_ID"
        if [ -z "$make_build_id" ]; then
            rlDie "Failed to get koji build ID for make"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Test artifact installation on Fedora"
        rlLog "Using koji build ID: $make_build_id"
        rlLog "Using repository URL: https://download.docker.com/linux/fedora/docker-ce.repo"

        # TODO: Handle VM, local and other provision also
        # Run all phases including execute to test that make gets installed via require
        rlRun "tmt run -i $run --scratch -vvv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --insert --how artifact \
               --provide koji.build:$make_build_id \
               --provide repository-file:https://download.docker.com/linux/fedora/docker-ce.repo" 0 "Run tmt with artifact providers"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
