#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"

        rlRun "export TMT_BOOT_TIMEOUT=300"
        rlRun "export TMT_CONNECT_TIMEOUT=300"
    rlPhaseEnd

    rlPhaseStartTest "Test with $PROVISION_HOW provisioning"
        rlRun "tmt -vv run -a provision --update --how $PROVISION_HOW"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
