#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup

        build_container_image "centos/7/upstream\:latest"
        build_container_image "fedora/latest:\latest"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    for image in $TEST_IMAGE_PREFIX/fedora/latest:latest \
                 $TEST_IMAGE_PREFIX/centos/7/upstream:latest; do
        # Prepare the tmt command and expected error message
        tmt="tmt run -avr provision -h $PROVISION_HOW"
        if [ "$PROVISION_HOW" = "container" ]; then
            tmt+=" -i $image"
        elif [ "$PROVISION_HOW" = "mock" ]; then
            tmt+=" -r fedora-rawhide-x86_64"
        fi
        if [[ $image =~ fedora || $PROVISION_HOW = "mock" ]]; then
            error='No match for argument: forest'
        else
            error='No package forest available'
        fi

        rlPhaseStartTest "Require an available package ($image)"
            rlRun -s "$tmt plan --name available"
            rlAssertGrep '2 preparations applied' $rlRun_LOG
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
