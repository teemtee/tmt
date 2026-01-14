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

        setup_fedora_environment

        # Get koji build ID for make
        get_koji_build_id "make" "f${fedora_release}"
        make_build_id="$KOJI_BUILD_ID"
        if [ -z "$make_build_id" ]; then
            rlDie "Failed to get koji build ID for make"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Test multiple providers with command-line override"
        rlRun "tmt run -i $run --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --how artifact \
                --provide koji.build:$make_build_id \
                --provide repository-file:https://download.docker.com/linux/fedora/docker-ce.repo" 0 "Run with multiple providers"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
