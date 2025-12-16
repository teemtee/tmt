#!/bin/bash
# Example test for using multiple artifact providers together
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

        # Get a build ID from koji for the first provider
        rlLog "Getting build ID for 'tree' package from koji"
        rlRun -s "koji list-tagged --latest f${fedora_release} tree"
        tree_nvr=$(tail -1 $rlRun_LOG | awk '{print $1}')
        rlRun "test -n '$tree_nvr'" 0 "Got NVR: $tree_nvr"

        rlRun -s "koji buildinfo $tree_nvr"
        tree_buildid=$(head -1 $rlRun_LOG | grep -oP '\[\K[0-9]+(?=\])')
        rlRun "test -n '$tree_buildid'" 0 "Got build ID: $tree_buildid"
    rlPhaseEnd

    rlPhaseStartTest "Use multiple providers together"
        # This demonstrates using multiple artifact providers in one prepare step
        # Usage: --provide <type1>:<value1> --provide <type2>:<value2> ...
        rlRun "tmt run -i $run --scratch -vv \
            plan --name /plans/example \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare -h artifact \
                --provide koji.build:$tree_buildid \
                --provide repository-url:https://download.docker.com/linux/fedora/docker-ce.repo \
            execute -h tmt --script 'rpm -q tree && rpm -q docker-ce-cli' \
            finish" 0 "Install packages from multiple providers"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
