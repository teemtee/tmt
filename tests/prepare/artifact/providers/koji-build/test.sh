#!/bin/bash
# Example test for koji.build artifact provider
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

        # Get a known good build ID from koji
        rlLog "Getting build ID for 'make' package from koji"
        rlRun -s "koji list-tagged --latest f${fedora_release} make"
        make_nvr=$(tail -1 $rlRun_LOG | awk '{print $1}')
        rlRun "test -n '$make_nvr'" 0 "Got NVR: $make_nvr"

        rlRun -s "koji buildinfo $make_nvr"
        make_buildid=$(head -1 $rlRun_LOG | grep -oP '\[\K[0-9]+(?=\])')
        rlRun "test -n '$make_buildid'" 0 "Got build ID: $make_buildid"
    rlPhaseEnd

    rlPhaseStartTest "Use koji.build provider to install package"
        # This demonstrates how to use the koji.build provider
        # Usage: prepare --how artifact --provide koji.build:<build_id>
        rlRun "tmt run -i $run --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare --how artifact --provide koji.build:$make_buildid" 0 "Install package from koji.build provider"

        # Verify make was installed from tmt-artifact-shared
        rlAssertGrep "tmt-artifact-shared" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
