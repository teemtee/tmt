#!/bin/bash
# Example test for using multiple artifact providers together
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
        build_container_image "fedora/${fedora_release}:latest"

        # Get a build ID from koji for the first provider
        rlLog "Getting build ID for 'make' package from koji"
        rlRun -s "koji list-tagged --latest f${fedora_release} make"
        make_nvr=$(tail -1 $rlRun_LOG | awk '{print $1}')
        rlRun "test -n '$make_nvr'" 0 "Got NVR: $make_nvr"

        rlRun -s "koji buildinfo $make_nvr"
        make_buildid=$(head -1 $rlRun_LOG | grep -oP '\[\K[0-9]+(?=\])')
        rlRun "test -n '$make_buildid'" 0 "Got build ID: $make_buildid"
    rlPhaseEnd

    rlPhaseStartTest "Use multiple providers together"
        # This demonstrates using multiple artifact providers in one prepare step
        # Usage: prepare --how artifact --provide <type1>:<value1> --provide <type2>:<value2>
        rlRun "tmt run -i $run --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare --how artifact \
                --provide koji.build:$make_buildid \
                --provide repository-url:https://download.docker.com/linux/fedora/docker-ce.repo" 0 "Install packages from multiple providers"

        # Verify both packages were handled correctly
        rlAssertGrep "make" "$run/log.txt"
        rlAssertGrep "docker-ce-cli" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
