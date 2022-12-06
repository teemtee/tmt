#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    for method in ${METHODS:-container}; do
        tmt="tmt run -vvvddd --all --remove provision --how $method"
        basic="plan --name 'mixed|weird'"
        debuginfo="plan --name debuginfo"

        # Verify against the default provision image
        rlPhaseStartTest "Test the default image ($method)"
            rlRun "$tmt $basic"
        rlPhaseEnd

        # Check CentOS images for container provision
        if [[ "$method" == "container" ]]; then
            for image in centos:7 centos:stream8; do
                rlPhaseStartTest "Test $image ($method)"
                    rlRun "$tmt --image $image $basic"
                rlPhaseEnd
            done
        fi
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
