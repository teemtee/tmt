#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

PROVISION_HOW=container

rlJournalStart
    rlPhaseStartSetup

        build_container_image "centos/7/upstream\:latest"
        build_container_image "fedora/40:\latest"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    for image in $TEST_IMAGE_PREFIX/fedora/40:latest \
                 $TEST_IMAGE_PREFIX/centos/7/upstream:latest; do
        # Prepare the tmt command and expected error message
        tmt="tmt run -avr provision -h $PROVISION_HOW -i $image"
        if [[ $image =~ fedora ]]; then
            error='No match for argument: forest'
        else
            error='No package forest available'
        fi

        rlPhaseStartTest "Require an available package ($image)"
            rlRun -s "$tmt plan --name available"
            rlAssertGrep '1 preparation applied' $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "Require a missing package ($image)"
            rlRun -s "$tmt plan --name missing" 2
            rlAssertGrep "$error" $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "Require both available and missing ($image)"
            rlRun -s "$tmt plan --name mixed" 2
            rlAssertGrep "$error" $rlRun_LOG
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "rm -f output"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
