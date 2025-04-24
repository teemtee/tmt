#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart "CRB Feature Test"
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        build_container_image "centos/stream9/upstream\:latest"
        build_container_image "ubi/8/upstream\:latest"

        rlRun "pushd data"
    rlPhaseEnd

    images="$TEST_IMAGE_PREFIX/centos/stream9/upstream:latest $TEST_IMAGE_PREFIX/ubi/8/upstream:latest ubi9"

    # CRB
    for image in $images; do
        # Run the '/crb/enabled' plan, overriding the provision image.
        # The plan itself contains the check (dnf repolist enabled | grep ...).
        # Expecting tmt run to succeed (exit code 0) as the check should pass.
        rlPhaseStartTest "Test /crb/enabled on $image"
            rlRun "tmt run --all provision --how container --image $image prepare execute plan --name /crb/enabled" 0 "Run /crb/enabled plan for $image"
        rlPhaseEnd

        # Run the '/crb/disabled' plan, overriding the provision image.
        # The plan itself contains the checks (! dnf repolist enabled ... && dnf repolist disabled ...).
        # Expecting tmt run to succeed (exit code 0) as the checks should pass.
        rlPhaseStartTest "Test /crb/disabled on $image"
            rlRun "tmt run --all provision --how container --image $image prepare execute plan --name /crb/disabled" 0 "Run /crb/disabled plan for $image"
        rlPhaseEnd

        # Run the '/crb_package' only on c9s
        if is_centos_stream_9 "$image"; then
            rlPhaseStartTest "Test /crb/crb_package on $image"
                # This plan enables CRB and tries to install a package from it.
                rlRun "tmt run --all provision --how container --image $image prepare execute plan --name /crb/crb_package" 0 "Run /crb/crb_package plan for $image"
            rlPhaseEnd
        fi
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
