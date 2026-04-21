#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart "CRB Feature Test"
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "IMAGE_MODE=${IMAGE_MODE:-no}"

        if [ "$PROVISION_HOW" = "container" ]; then
            build_container_image "centos/stream9/upstream\:latest"
            build_container_image "ubi/8/upstream\:latest"
            build_container_image "fedora/latest\:latest"
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

    # CRB
    while IFS= read -r image; do
        if is_fedora "$image"; then
            # Test Fedora for the warning message
            rlPhaseStartTest "Test warning on $image"
                # Run a CRB plan (just provision, prepare and finish) on fedora and verify the warning is shown
                # We expect the tmt run to succeed (exit code 0) because it's a warning, not an error.
                rlRun -s "tmt run provision --how $PROVISION_HOW --image $image prepare finish plan --name /crb/enabled" 0 "Run plan on fedora and capture output"
                rlAssertGrep "CRB prepare feature is supported on RHEL/CentOS-Stream 8, 9 or 10." $rlRun_LOG
            rlPhaseEnd
        else
            # Run the '/crb/enabled' plan, overriding the provision image.
            # The plan itself contains the check (dnf repolist enabled | grep ...).
            # Expecting tmt run to succeed (exit code 0) as the check should pass.
            rlPhaseStartTest "Test /crb/enabled on $image"
                rlRun "tmt run --all provision --how $PROVISION_HOW --image $image plan --name /crb/enabled" 0 "Run /crb/enabled plan for $image"
            rlPhaseEnd

            # Run the '/crb/disabled' plan, overriding the provision image.
            # The plan itself contains the checks (! dnf repolist enabled ... && dnf repolist disabled ...).
            # Expecting tmt run to succeed (exit code 0) as the checks should pass.
            rlPhaseStartTest "Test /crb/disabled on $image"
                rlRun "tmt run --all provision --how $PROVISION_HOW --image $image plan --name /crb/disabled" 0 "Run /crb/disabled plan for $image"
            rlPhaseEnd

            # Run the '/crb_package' only on c9s
            if is_centos_stream_9 "$image"; then
                rlPhaseStartTest "Test /crb/crb_package on $image"
                    # This plan enables CRB and tries to install a package from it.
                    rlRun "tmt run --all provision --how $PROVISION_HOW --image $image prepare execute plan --name /crb/crb_package" 0 "Run /crb/crb_package plan for $image"
                rlPhaseEnd
            fi
        fi
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
