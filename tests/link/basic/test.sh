#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create a tmp directory"
        rlRun "pushd $tmp"
        rlRun "tmt init"
    rlPhaseEnd

    rlPhaseStartTest "Create Test"
        rlRun "tmt test create /test/created --template shell --link verifies:/feature/one"
        rlRun -s "tmt test show /test/created"
        rlAssertGrep "verifies /feature/one" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Existing Test"
        rlRun "tmt test create /test/existing --template shell"
        rlRun "tmt link /test/existing --link verifies:/feature/two"
        rlRun "tmt link /test/existing --link verifies:/feature/three"
        rlRun -s "tmt test show /test/existing"
        rlAssertGrep "verifies /feature/two" $rlRun_LOG
        rlAssertGrep "verifies /feature/three" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "No Link Provided"
        rlRun -s "tmt link /test/existing" 2
        rlAssertGrep "Provide at least one link" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove the tmp directory"
    rlPhaseEnd
rlJournalEnd
