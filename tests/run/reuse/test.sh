#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run_dir=\$(mktemp -d -p /var/tmp/tmt)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "tmt run --id $run_dir provision -h virtual"
        rlRun "tmt run --id $run_dir discover prepare"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "tmt run --id $run_dir finish"
        rlRun "rm -rf $run_dir" 0 "Remove run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
