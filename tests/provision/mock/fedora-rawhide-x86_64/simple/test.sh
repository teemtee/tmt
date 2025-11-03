#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd ../data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "TMT_SHOW_TRACEBACK=1 tmt --feeling-safe run --id $run test --name /test/os-release -vvv"
        rlAssertGrep "NAME.*Fedora Linux" $run/plan/execute/data/guest/default-0/test/os-release-1/output.txt
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
