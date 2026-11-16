#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

PROVISION_HOW=container

rlJournalStart
    rlPhaseStartSetup
        rlRun "IMAGES='$TEST_CONTAINER_IMAGES'"

        build_container_image "centos/7/upstream\:latest"
        build_container_image "centos/6/upstream\:latest"
        build_container_image "fedora/latest\:latest"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    package_to_test_error="Required packages failed to install, aborting:
                forest: required by: /test/missing"

    for image in $TEST_IMAGE_PREFIX/fedora/latest:latest $IMAGES; do
        # Prepare the tmt command and expected error message
        tmt="tmt run -avr provision -h $PROVISION_HOW -i $image"
        if [[ "$image" == "$TEST_IMAGE_PREFIX/fedora/latest:latest" ]]; then
            error='No match for argument: forest'
        elif is_centos_6 "$image" || is_centos_7 "$image"; then
            error='No package forest available'
        else
            continue
        fi

        rlPhaseStartTest "Require an available package ($image)"
            rlRun -s "$tmt plan --name available"
            rlAssertGrep '2 preparations applied' $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "Require a missing package ($image)"
            rlRun -s "$tmt plan --name missing" 2
            rlAssertGrep "$error" $rlRun_LOG
            rlAssertGrep "$package_to_test_error" $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "Require both available and missing ($image)"
            rlRun -s "$tmt plan --name mixed" 2
            rlAssertGrep "$error" $rlRun_LOG
            rlAssertGrep "$package_to_test_error" $rlRun_LOG
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "rm -f output"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
