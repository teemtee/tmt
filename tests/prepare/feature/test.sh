#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    # EPEL
    for method in ${PROVISION_METHODS:-"container"}; do
        for image in "centos:stream9"; do
            rlPhaseStartTest "Enable EPEL"
                rlRun -s "tmt -vvv run -a plan --name '/epel/enabled'  provision --how $method --image $image"
            rlPhaseEnd

            rlPhaseStartTest "Disable EPEL"
                rlRun -s "tmt -vvv run -a plan --name '/epel/disabled' provision --how $method --image $image"
            rlPhaseEnd
        done
    done

    # CRB
    # for method in ${PROVISION_METHODS:-"container"}; do
    #     for image in "centos:stream9"; do
    #         rlPhaseStartTest "Enable CRB"
    #             rlRun -s "tmt -vvv run -a plan --name '/crb/enabled' provision --how $method --image $image"
    #         rlPhaseEnd
    #
    #         rlPhaseStartTest "Disable CRB"
    #             rlRun -s "tmt -vvv run -a plan --name '/crb/disabled' provision --how $method --image $image"
    #         rlPhaseEnd
    #     done
    # done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
