#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd ../shared-data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        if ! rlIsFedora; then
          # TODO: Handle centos artifacts also
          rlDie "Skipping because non-fedora test is not implemented"
        fi
        rlRun "fedora_release=43"
        build_container_image "fedora/${fedora_release}:latest"

        # Get koji build info
        rlRun -s "koji list-tagged --latest f${fedora_release} make" 0 "Get the latest make build"
        if [[ ! "$(tail -1 $rlRun_LOG)" =~ ^([^[:space:]]+) ]]; then
            rlDie "Package NVR regex failed"
        fi
        rlRun "make_nvr=${BASH_REMATCH[1]}" 0 "Get the package NVR"
        rlRun -s "koji buildinfo $make_nvr" 0 "Get the build info"
        if [[ ! "$(head -1 $rlRun_LOG)" =~ ^BUILD:[[:space:]]*[^[:space:]]+[[:space:]]*\[([[:digit:]]+)\] ]]; then
            rlDie "BuildID regex failed"
        fi
        rlRun "make_buildid=${BASH_REMATCH[1]}" 0 "Get the make build ID"
    rlPhaseEnd

    rlPhaseStartTest "Test koji provider"
        rlRun "tmt run -i $run --scratch -avvv \
            --environment REPO_LIST=tmt-artifact-shared \
            --environment ARTIFACT_LIST=make \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare --insert --how artifact --provide koji.build:$make_buildid" \
            0 "Test koji.build provider"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
