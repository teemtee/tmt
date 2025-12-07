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

        # Use Docker CE repository which is publicly available
        rlRun "repo_url=https://download.docker.com/linux/fedora/docker-ce.repo"
    rlPhaseEnd

    rlPhaseStartTest "Test repository-url provider"
        rlRun "tmt run -i $run --scratch -avvv \
            --environment REPO_LIST=docker-ce-stable \
            --environment ARTIFACT_LIST=docker-ce \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare --insert --how artifact \
                --provide repository-url:$repo_url" \
            0 "Test repository-url provider"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
