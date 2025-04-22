#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        build_container_image "centos/stream9/upstream\:latest"
        build_container_image "ubi/8/upstream\:latest"

        rlRun "pushd data"
    rlPhaseEnd

    images="$TEST_IMAGE_PREFIX/centos/stream9/upstream:latest $TEST_IMAGE_PREFIX/ubi/8/upstream:latest ubi9"

    # EPEL
    for image in $images; do
        if rlIsFedora ">=42" && (is_centos_7 "$image" || is_ubi_8 "$image"); then
            rlLogInfo "Skipping because Ansible shipped with Fedora does not support Python 3.6"

            continue
        fi

        rlPhaseStartTest "Enable EPEL on $image"
            rlRun -s "tmt -vvv run -a plan --name '/epel/enabled' provision --how container --image $image"
        rlPhaseEnd

        rlPhaseStartTest "Disable EPEL on $image"
            rlRun -s "tmt -vvv run -a plan --name '/epel/disabled' provision --how container --image $image"
        rlPhaseEnd

        if is_centos_stream_9 "$image"; then
            rlPhaseStartTest "Check CRB on $image"
                rlRun -s "tmt -vvv run -a plan --name '/flac' provision --how container --image $image"
            rlPhaseEnd
        fi
    done

    # Environment profiles
    # TODO: chicken and egg: we need profile to test whether tmt can apply it, and we need tmt
    # with support for profiles so we could test profiles and start shipping them...
    # Once we get the tmt, we can continue with profiles and eventually enable the test below.
    #
    # rlPhaseStartTest "Enable EPEL on $image"
    #     rlRun -s "tmt -vvv run -a plan --name '/profile' provision --how container --image fedora"
    # rlPhaseEnd


    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
