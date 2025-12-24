#!/bin/bash
# Example test for repository-url artifact provider
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        if ! rlIsFedora; then
            rlDie "Test requires Fedora"
        fi

        fedora_release=43
        build_container_image "fedora/${fedora_release}:latest"
    rlPhaseEnd

    rlPhaseStartTest "Use repository-url provider to enable external repo"
        # This demonstrates how to use the repository-url provider
        # Usage: --provide repository-url:<repo_url>
        rlRun "tmt run -i $run --scratch -vv \
            plan --name /plans/example \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare -h artifact --provide repository-url:https://download.docker.com/linux/fedora/docker-ce.repo \
            execute -h tmt --script 'dnf install -y docker-ce-cli && rpm -q docker-ce-cli' \
            finish" 0 "Install package from external repository"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
