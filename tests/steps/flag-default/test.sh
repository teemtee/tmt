#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Flag fields set to null in fmf resolve to declared defaults"
        rlRun -s "tmt plan show -vv"
        rlAssertGrep "open false" $rlRun_LOG
        rlAssertGrep "absolute-paths false" $rlRun_LOG
        rlAssertGrep "exit-first false" $rlRun_LOG
        rlAssertGrep "check-first true" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
