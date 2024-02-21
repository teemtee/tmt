#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test with provision $PROVISION_HOW"
        rlRun "tmt run --scratch -vvi $run -a provision -h $PROVISION_HOW --ssh-option ServerAliveCountMax=123456789"
        rlAssertGrep "Run command: ssh .*-oServerAliveCountMax=123456789" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
