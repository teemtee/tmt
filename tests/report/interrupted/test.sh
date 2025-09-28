#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test bash breakage method"
        rlRun -s "tmt run -e weird_method=bash -vvv --id $run" 2

        # Tests before the breakage are executed as expected
        rlAssertGrep "pass /test/good" $rlRun_LOG
        rlAssertGrep "fail /test/bad" $rlRun_LOG
        rlAssertGrep "errr /test/weird" $rlRun_LOG

        # Report is generated
        rlAssertGrep "^\s*report\s*$" $rlRun_LOG
        rlAssertGrep "how: html" $rlRun_LOG
        rlAssertGrep "output: /.*/plan/report/default-0/index.html" $rlRun_LOG
        rlAssertGrep "summary: 1 test passed, 1 test failed, 1 error and 1 pending" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test ssh breakage method"
        rlRun -s "tmt run --scratch -e weird_method=ssh -vvv --id $run" 2

        # Tests before the breakage are executed as expected
        rlAssertGrep "pass /test/good" $rlRun_LOG
        rlAssertGrep "fail /test/bad" $rlRun_LOG
        rlAssertGrep "errr /test/weird" $rlRun_LOG
        # In this case `/test/missed` would not be missing because we
        # are only killing the `/test/weird`'s sshd-session
        rlAssertGrep "pass /test/missed" $rlRun_LOG

        # Report is generated
        rlAssertGrep "^\s*report\s*$" $rlRun_LOG
        rlAssertGrep "how: html" $rlRun_LOG
        rlAssertGrep "output: /.*/plan/report/default-0/index.html" $rlRun_LOG
        rlAssertGrep "summary: 2 tests passed, 1 test failed and 1 error" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
