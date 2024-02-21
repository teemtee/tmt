#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
    rlPhaseEnd

    tmt="tmt run --all --remove provision --how $PROVISION_HOW"
    basic="plan --name 'mixed|weird'"
    debuginfo="plan --name debuginfo"

    # Verify against the default provision image
    rlPhaseStartTest "Test the default image ($PROVISION_HOW)"
        rlRun "$tmt $basic"
    rlPhaseEnd

    # Check CentOS images for container provision
    if [[ "$PROVISION_HOW" == "container" ]]; then
        for image in centos:7 centos:stream8; do
            rlPhaseStartTest "Test $image ($PROVISION_HOW)"
                rlRun "$tmt --image $image $basic"
            rlPhaseEnd
        done
    fi

    # Check debuginfo install (only for supported distros)
    # https://bugzilla.redhat.com/show_bug.cgi?id=1964505
    if [[ "$PROVISION_HOW" == "container" ]]; then
        for image in fedora centos:7; do
            rlPhaseStartTest "Test $image ($PROVISION_HOW) [debuginfo]"
                rlRun "$tmt --image $image $debuginfo"
            rlPhaseEnd
        done
    fi

    # Add one extra CoreOS run for virtual provision
    if [[ "$PROVISION_HOW" == "virtual" ]]; then
        rlPhaseStartTest "Test fedora-coreos ($PROVISION_HOW)"
            rlRun "$tmt --image fedora-coreos $basic"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
