#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

IMAGE_NEEDS_DEPS="localhost/tmt-bootc-needs-deps"
IMAGE_INCLUDES_DEPS="localhost/tmt-bootc-includes-deps"


rlJournalStart
    rlPhaseStartSetup
        # Use /var/tmp/tmt so the temp directories are accessible
        # in the podman machine mount
        rlRun "mkdir -p /var/tmp/tmt"
        rlRun "run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"
        rlRun "dry_run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create dry run directory"
        rlRun "pushd data"
        rlRun "df -h" 0 "Check available disk space"
        build_container_image "fedora/latest/bootc\:latest"
    rlPhaseEnd

    # This test must be ran first, or podman machine and container image will exist.
    rlPhaseStartTest "Test dry run for bootc works as expected"
        rlRun -s "tmt -vvv run --dry --scratch -i $dry_run provision -h bootc --container-image $TEST_IMAGE_PREFIX/fedora/latest/bootc:latest"
        rlRun "ls $dry_run/plans/containerfile/includes-deps/provision/default-0/ | grep qcow2" "1"
        rlRun "podman machine ls  | grep podman-machine-tmt" "1"
        rlRun "podman images | grep localhost/tmtmodified" "1"
    rlPhaseEnd

    rlPhaseStartTest "Image that needs dependencies"
        rlRun "podman build . -f needs-deps.containerfile -t $IMAGE_NEEDS_DEPS"
        rlRun -s "tmt -vvv run --scratch -i $run plan --name /plans/image/needs-deps"
        # Testing the output of the bootc package manager
        rlAssertGrep "building container image with dependencies" $rlRun_LOG
        rlAssertGrep "STEP 1/2: FROM containers-storage:localhost/tmt/bootc" $rlRun_LOG
        rlAssertGrep "Successfully tagged localhost/tmt/bootc/" $rlRun_LOG
        rlAssertGrep "switching to new image localhost/tmt/bootc/" $rlRun_LOG
        rlAssertGrep "rebooting to apply new image" $rlRun_LOG

    rlPhaseEnd

    rlPhaseStartTest "Image that already includes dependencies"
        rlRun "podman build . -f includes-deps.containerfile -t $IMAGE_INCLUDES_DEPS"
        rlRun -s "tmt -vvv run --scratch -i $run plan --name /plans/image/includes-deps"
        # Testing the output of the bootc package manager
        rlAssertGrep "building container image with dependencies" $rlRun_LOG
        rlAssertGrep "STEP 1/2: FROM containers-storage:localhost/tmt-bootc-includes-deps" $rlRun_LOG
        rlAssertGrep "Successfully tagged localhost/tmt/bootc/" $rlRun_LOG
        rlAssertGrep "switching to new image localhost/tmt/bootc/" $rlRun_LOG
        rlAssertGrep "rebooting to apply new image" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Containerfile that needs dependencies"
        rlRun -s "tmt -vvv run --scratch -i $run plan --name /plans/containerfile/needs-deps"
        # Testing the output of the bootc package manager
        rlAssertGrep "building container image with dependencies" $rlRun_LOG
        rlAssertGrep "STEP 1/2: FROM containers-storage:localhost/tmtmodified" $rlRun_LOG
        rlAssertGrep "Successfully tagged localhost/tmt/bootc/" $rlRun_LOG
        rlAssertGrep "switching to new image localhost/tmt/bootc/" $rlRun_LOG
        rlAssertGrep "rebooting to apply new image" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Containerfile that already includes dependencies"
        rlRun -s "tmt -vvv run --scratch -i $run plan --name /plans/containerfile/includes-deps"
        # Testing the output of the bootc package manager
        rlAssertGrep "building container image with dependencies" $rlRun_LOG
        rlAssertGrep "STEP 1/2: FROM containers-storage:localhost/tmtbase-" $rlRun_LOG
        rlAssertGrep "Successfully tagged localhost/tmt/bootc/" $rlRun_LOG
        rlAssertGrep "switching to new image localhost/tmt/bootc/" $rlRun_LOG
        rlAssertGrep "rebooting to apply new image" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
        rlRun "rm -r $dry_run" 0 "Remove dry run directory"
        rlRun "podman rmi $IMAGE_INCLUDES_DEPS" 0,1
        rlRun "podman rmi $IMAGE_NEEDS_DEPS" 0,1
    rlPhaseEnd
rlJournalEnd
