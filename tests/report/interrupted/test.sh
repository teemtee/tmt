#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run -vvv --id $run" 2

        # Tests before the breakage are executed as expected
        rlAssertGrep "pass /test/good" $rlRun_LOG
        rlAssertGrep "fail /test/bad" $rlRun_LOG

        # Report is generated
        rlAssertGrep "^\s*report\s*$" $rlRun_LOG
        rlAssertGrep "how: html" $rlRun_LOG
        rlAssertGrep "output: /.*/plan/report/default-0/index.html" $rlRun_LOG
        rlAssertGrep "summary: 1 test passed and 1 test failed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
