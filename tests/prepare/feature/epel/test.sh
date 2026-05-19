#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

CONTAINER_IMAGES="centos/stream9/upstream:latest
ubi/8/upstream:latest
ubi/9/upstream:latest"

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "IMAGE_MODE=${IMAGE_MODE:-no}"

        if [ "$PROVISION_HOW" = "container" ]; then
            for image in $CONTAINER_IMAGES; do
                build_container_image "$image"
            done
            rlRun "IMAGES='$CONTAINER_IMAGES'"
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

    while IFS= read -r image; do
        [ "$PROVISION_HOW" = "container" ] && image="$TEST_IMAGE_PREFIX/$image"

        if is_fedora "$image"; then
            # Test Fedora for the warning message
            rlPhaseStartTest "Test warning on $image"
                # Run a epel plan (just provision, prepare and finish) on fedora and verify the warning is shown
                # We expect the tmt run to succeed (exit code 0) because it's a warning, not an error.
                rlRun -s "tmt run provision --how $PROVISION_HOW --image $image prepare finish plan --name /epel/enabled/default" 0 "Run plan on fedora and capture output"
                rlAssertGrep "EPEL·prepare·feature·is·supported·on·RHEL/CentOS-Stream·8+." $rlRun_LOG
            rlPhaseEnd

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

        rlPhaseStartTest "Check if CRB enabled with EPEL on $image"
            rlRun -s "tmt -vvv run -a plan --name '/gdbm' provision --how $PROVISION_HOW --image $image"
        rlPhaseEnd
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
