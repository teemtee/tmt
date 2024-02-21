#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"

        rlRun "export TMT_BOOT_TIMEOUT=300"
        rlRun "export TMT_CONNECT_TIMEOUT=300"
    rlPhaseEnd

    rlPhaseStartTest "Test with $PROVISION_HOW provisioning"
        rlRun "tmt -vv run --id $run --all provision --update --how $PROVISION_HOW"
        rlFileSubmit "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
