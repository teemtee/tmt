#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

IMAGE_NEEDS_DEPS="localhost/tmt-bootc-needs-deps"
IMAGE_NEEDS_DEPS_PLAN="$(pwd)/data/image_needs_deps.fmf"
IMAGE_INCLUDES_DEPS="localhost/tmt-bootc-includes-deps"
IMAGE_INCLUDES_DEPS_PLAN="$(pwd)/data/image_includes_deps.fmf"

CONTAINERFILE_NEEDS_DEPS="$(pwd)/data/needs_deps.containerfile"
CONTAINERFILE_NEEDS_DEPS_PLAN="$(pwd)/data/containerfile_needs_deps.fmf"
CONTAINERFILE_INCLUDES_DEPS="$(pwd)/data/includes_deps.containerfile"
CONTAINERFILE_INCLUDES_DEPS_PLAN="$(pwd)/data/containerfile_includes_deps.fmf"


rlJournalStart
    rlPhaseStartSetup
        # cleanup previous runs
        test -d /var/tmp/tmt/testcloud && rlRun "rm -rf /var/tmp/tmt/testcloud"

        # use /var/tmp/tmt so the temp directories are accessible
        # in the podman machine mount
        rlRun "tmp=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init"
    rlPhaseEnd

    rlPhaseStartTest "Image that needs dependencies"
        rlRun "podman build . -f $CONTAINERFILE_NEEDS_DEPS -t $IMAGE_NEEDS_DEPS"
        rlRun "cp $IMAGE_NEEDS_DEPS_PLAN ."
        rlRun "tmt -vvvvv run -i $run"
    rlPhaseEnd

    rlPhaseStartTest "Image that already includes dependencies"
        rlRun "podman build . -f $CONTAINERFILE_INCLUDES_DEPS -t $IMAGE_INCLUDES_DEPS"
        rlRun "cp $IMAGE_INCLUDES_DEPS_PLAN ."
        rlRun "tmt -vvvvv run -i $run"
    rlPhaseEnd

    rlPhaseStartTest "Containerfile that needs dependencies"
        rlRun "cp $CONTAINERFILE_NEEDS_DEPS_PLAN ."
        rlRun "cp $CONTAINERFILE_NEEDS_DEPS $run"
        rlRun "tmt -vvvvv run --environment TMT_BOOTC_CONTAINERFILE_RUNDIR=$run -i $run"
    rlPhaseEnd

    rlPhaseStartTest "Containerfile that already includes dependencies"
        rlRun "cp $CONTAINERFILE_INCLUDES_DEPS_PLAN ."
        rlRun "cp $CONTAINERFILE_INCLUDES_DEPS $run"
        rlRun "tmt -vvvvv run --environment TMT_BOOTC_CONTAINERFILE_RUNDIR=$run -i $run"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $run" 0 "Remove run directory"

        rlRun "podman rmi $IMAGE_INCLUDES_DEPS" 0,1
        rlRun "podman rmi $IMAGE_NEEDS_DEPS" 0,1

        test -d /var/tmp/tmt/testcloud && rlRun "rm -rf /var/tmp/tmt/testcloud"
    rlPhaseEnd
rlJournalEnd
