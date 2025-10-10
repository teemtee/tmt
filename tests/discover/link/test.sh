#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "tmt='tmt run -v --id run --scratch'"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test the link key in the plan (single)"
        rlRun -s "$tmt plan --name single"
        rlAssertGrep '1 test selected' $rlRun_LOG
        rlAssertGrep '/tests/related' $rlRun_LOG
        rlAssertNotGrep '/tests/irrelevant' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test the link key in the plan (multiple)"
        rlRun -s "$tmt plan --name multiple"
        rlAssertGrep '2 tests selected' $rlRun_LOG
        rlAssertGrep '/tests/related' $rlRun_LOG
        rlAssertGrep '/tests/verifying' $rlRun_LOG
        rlAssertNotGrep '/tests/irrelevant' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test --link from the command line (single)"
        for relation in "" "relates:" "rel.*:"; do
            rlRun -s "$tmt plans --default discover --how fmf --link ${relation}/tmp/foo"
            rlAssertGrep '1 test selected' $rlRun_LOG
            rlAssertGrep '/tests/related' $rlRun_LOG
        done
    rlPhaseEnd

    rlPhaseStartTest "Test --link from the command line (multiple)"
        for relation in "verifies:https://github.com/teemtee/tmt/issues/870" \
                "ver.*:.*/issues/870" ".*/issues/870"; do
            rlRun -s "$tmt plans --default discover --how fmf --link $relation --link rubbish"
            rlAssertGrep '1 test selected' $rlRun_LOG
            rlAssertGrep '/tests/verifying' $rlRun_LOG
        done
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
