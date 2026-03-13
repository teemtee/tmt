#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Verify rsync uses --temp-dir option ($PROVISION_HOW)"
        rlRun "tmt -vv run -i $run -a provision -h $PROVISION_HOW"
        rlAssertGrep "Run command: rsync -ar --temp-dir $run/tmp/rsync-.*" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
