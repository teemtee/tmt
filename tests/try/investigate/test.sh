#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "export TMT_NO_COLOR=1"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Interactive Investigation"
        rlRun -s "LANG=en_US ./investigate.exp" 0 "Try interactive investigation"
        rlAssertGrep "2 tests executed" $rlRun_LOG
        rlAssertGrep "tmt-test-wrapper.sh" $rlRun_LOG
        rlAssertGrep "everything bad done" $rlRun_LOG
        rlAssertGrep "fail /tests/bad" $rlRun_LOG
        rlAssertGrep "everything good done" $rlRun_LOG
        rlAssertGrep "pass /tests/good" $rlRun_LOG
        rlAssertNotGrep "cannot set terminal process group" $rlRun_LOG
        rlAssertNotGrep "no job control in this shell" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
