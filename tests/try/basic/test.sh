#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "config=$(realpath config)"
        rlRun "export TMT_NO_COLOR=1"
        rlRun "pushd data"
    rlPhaseEnd


    rlPhaseStartTest "Local change directory"
        rlRun "cd tests/base/bad"
        rlRun "../../../lcd.exp"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -f config/last-run"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
