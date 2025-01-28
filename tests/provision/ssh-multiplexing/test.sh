#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "long_run=\$(mktemp -d /tmp/tmp.veryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryverylongXXX)" 0 "Create run directory with a very long name"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "SSH multiplexing should be enabled by default ($PROVISION_HOW)"
        rlRun "tmt -vv run -i $run -a provision -h $PROVISION_HOW"
        rlAssertGrep "Spawning the SSH master process" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartTest "SSH multiplexing should be disabled when SSH socket path gets too long ($PROVISION_HOW)"
        rlRun "tmt -vv run -i $long_run -a provision -h $PROVISION_HOW"
        rlAssertGrep "warn: SSH multiplexing will not be used because the SSH master socket path '.*' is too long." "$long_run/log.txt"
        rlAssertGrep "The SSH master process cannot be terminated because it is disabled." "$long_run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
        rlRun "rm -r $long_run" 0 "Remove run directory with the long name"
    rlPhaseEnd
rlJournalEnd
