#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run -vvv --id $run --all provision --how $PROVISION_HOW"
        rlAssertGrep "this is test output" $rlRun_LOG

        # Helper script actions should not appear in the verbose output
        rlAssertNotGrep "mkdir -p /usr/local/bin" $rlRun_LOG
        rlAssertNotGrep "rsync.*--version" $rlRun_LOG
    rlPhaseEnd

    # TODO Move verbosity level checks from /tests/execute/basic here

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
