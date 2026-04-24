#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
        rlRun "PROVISION_HOW=container"
        build_container_image "centos/stream10/upstream:latest"
    rlPhaseEnd

    rlPhaseStartTest
        image="$TEST_IMAGE_PREFIX/centos/stream10/upstream:latest"
        rlRun "tmt run --id $run -vvv --all provision --how container --image $image"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
