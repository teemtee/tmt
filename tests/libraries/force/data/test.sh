#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "rlImport --all"
        rlRun "cat $BEAKERLIB_DIR/metadata.yaml" 0 "Check metadata.yaml content"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "fileCreate $tmp/something"
        rlAssertExists "$tmp/something"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
