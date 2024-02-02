#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    images="centos:stream9 centos:stream8 ubi9 ubi8"

    # EPEL
    for image in $images; do
        rlPhaseStartTest "Enable EPEL on $image"
            rlRun -s "tmt -vvv run -a plan --name '/epel/enabled' provision --how container --image $image"
        rlPhaseEnd

        rlPhaseStartTest "Disable EPEL on $image"
            rlRun -s "tmt -vvv run -a plan --name '/epel/disabled' provision --how container --image $image"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
