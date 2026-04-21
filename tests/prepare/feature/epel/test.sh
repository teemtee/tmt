#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "IMAGE_MODE=${IMAGE_MODE:-no}"

        if [ "$PROVISION_HOW" = "container" ]; then
            build_container_image "centos/stream9/upstream\:latest"
            build_container_image "ubi/8/upstream\:latest"
            rlRun "IMAGES='$TEST_IMAGE_PREFIX/centos/stream9/upstream:latest $TEST_IMAGE_PREFIX/ubi/8/upstream:latest ubi9'"
        elif [ "$PROVISION_HOW" = "virtual" ]; then
            if [ "$IMAGE_MODE" = "yes" ]; then
                rlRun "IMAGES='$TEST_IMAGE_MODE_IMAGES'"
            else
                rlRun "IMAGES='$TEST_VIRTUAL_IMAGES'"
            fi
        else
            rlDie "Test supported only on containers or VMs"
        fi

        rlRun "pushd data"
    rlPhaseEnd

    # EPEL
    while IFS= read -r image; do
        if is_fedora "$image"; then
            rlLogInfo "Skipping Fedora for testing EPEL"
            continue
        fi

        rlPhaseStartTest "Enable EPEL on $image"
            rlRun -s "tmt -vvv run -a plan --name '/epel/enabled/default' provision --how $PROVISION_HOW --image $image"
        rlPhaseEnd

        rlPhaseStartTest "Enable EPEL on $image (epel pre-installed)"
            rlRun -s "tmt -vvv run -a plan --name '/epel/enabled/with-epel-preinstalled' provision --how $PROVISION_HOW --image $image"
        rlPhaseEnd

        rlPhaseStartTest "Disable EPEL on $image"
            rlRun -s "tmt -vvv run -a plan --name '/epel/disabled' provision --how $PROVISION_HOW --image $image"
        rlPhaseEnd

        if is_centos_stream_9 "$image"; then
            rlPhaseStartTest "Check CRB on $image"
                rlRun -s "tmt -vvv run -a plan --name '/flac' provision --how $PROVISION_HOW --image $image"
            rlPhaseEnd
        fi
    done <<< "$IMAGES"

    # Environment profiles
    # TODO: chicken and egg: we need profile to test whether tmt can apply it, and we need tmt
    # with support for profiles so we could test profiles and start shipping them...
    # Once we get the tmt, we can continue with profiles and eventually enable the test below.
    #
    # rlPhaseStartTest "Enable EPEL on $image"
    #     rlRun -s "tmt -vvv run -a plan --name '/profile' provision --how $PROVISION_HOW --image fedora"
    # rlPhaseEnd


    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
