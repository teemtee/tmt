#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    # Split provision and prepare steps into separate processes
    rlPhaseStartTest
        rlRun -s "TMT_SHOW_TRACEBACK=1 tmt --feeling-safe run --id $run -vvv discover provision"
        rlAssertGrep "NAME.*Fedora Linux" $rlRun_LOG
        rlRun -s "TMT_SHOW_TRACEBACK=1 tmt --feeling-safe run --id $run -vvv prepare execute report"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
