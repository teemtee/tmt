#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

IMAGE_NEEDS_DEPS="localhost/tmt-bootc-needs-deps"
IMAGE_INCLUDES_DEPS="localhost/tmt-bootc-includes-deps"


rlJournalStart
    rlPhaseStartSetup
        # Use /var/tmp/tmt so the temp directories are accessible
        # in the podman machine mount
        rlRun "mkdir -p /var/tmp/tmt"
        rlRun "run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Image that needs dependencies"
        rlRun "podman build . -f needs-deps.containerfile -t $IMAGE_NEEDS_DEPS"
        rlRun "tmt -vvv run --scratch -i $run plan --name /plans/image/needs-deps"
    rlPhaseEnd

    rlPhaseStartTest "Image that already includes dependencies"
        rlRun "podman build . -f includes-deps.containerfile -t $IMAGE_INCLUDES_DEPS"
        rlRun "tmt -vvv run --scratch -i $run plan --name /plans/image/includes-deps"
    rlPhaseEnd

    rlPhaseStartTest "Containerfile that needs dependencies"
        rlRun "tmt -vvv run --scratch -i $run plan --name /plans/containerfile/needs-deps"
    rlPhaseEnd

    rlPhaseStartTest "Containerfile that already includes dependencies"
        rlRun "tmt -vvv run --scratch -i $run plan --name /plans/containerfile/includes-deps"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
        rlRun "podman rmi $IMAGE_INCLUDES_DEPS" 0,1
        rlRun "podman rmi $IMAGE_NEEDS_DEPS" 0,1
    rlPhaseEnd
rlJournalEnd
