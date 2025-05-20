#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "tmp=\$(mktemp -d)" 0 "Create a tmp directory"
        rlRun "pushd $tmp"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "tmt run --id $run provision --how beaker"
        rlRun "tmt run --id $run login --command 'echo ok'"
        rlRun "tmt run --id $run finish"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run $tmp" 0 "Remove testing directories"
    rlPhaseEnd
rlJournalEnd
