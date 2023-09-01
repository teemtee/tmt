#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd prune"
        rlRun "run=\$(mktemp -d)"
    rlPhaseEnd

    rlPhaseStartTest "Discover only"
        rlRun -s "tmt run -i $run discover tests --name test1"
        rlAssertExists "$run/plan/discover/default-0/tests/test1"
        rlAssertNotExists "$run/plan/discover/default-0/tests/test2"
        rlAssertNotExists "$run/plan/discover/default-0/tests/some-file"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
