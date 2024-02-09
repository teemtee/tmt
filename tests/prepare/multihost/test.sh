#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"

        rlRun "export TMT_BOOT_TIMEOUT=300"
        rlRun "export TMT_CONNECT_TIMEOUT=300"
    rlPhaseEnd

    for method in ${PROVISION_METHODS:-container}; do
        rlPhaseStartTest "Test with $method provisioning"
            rlRun "tmt -vv run -a provision --update --how $method"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
