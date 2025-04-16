#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd local-and-remote"
    rlPhaseEnd

    rlPhaseStartTest "Show plan"
        rlRun -s "tmt plan show"

        rlAssertGrep "warn: Plan '/' defines both 'execute' and 'import', ignoring the 'execute' step." $rlRun_LOG
        rlAssertEquals "There should be only one plan reported" \
            "$(grep -E '^/' $rlRun_LOG | wc -l)" "1"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
