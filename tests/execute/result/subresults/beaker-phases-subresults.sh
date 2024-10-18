#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1


rlJournalStart
    rlPhaseStartSetup "phase-setup"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
    rlPhaseEnd

    rlPhaseStartTest "Internal test of environment variable values"
        rlRun "test -n \"\$TMT_TEST_SERIAL_NUMBER\" -o -n \"\$TESTID\"" 0 "Check the variables are not empty"
        rlAssertEquals "TESTID must be set to TMT_TEST_SERIAL_NUMBER" "$TESTID" "$TMT_TEST_SERIAL_NUMBER"

        rlRun "[[ \$BEAKERLIB_COMMAND_REPORT_RESULT =~ tmt-report-result$ ]]" 0 "Check the variable contains path to a tmt-report-result script"
    rlPhaseEnd

    rlPhaseStartTest "phase-test pass"
        rlRun -s "echo mytest-pass" 0 "Check output"
        rlAssertGrep "mytest-pass" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "phase-test fail"
        rlRun -s "echo mytest-fail" 0 "Check output"
        rlAssertGrep "asdf-asdf" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "phase-test multiple tmt-report-result"
        rlRun "touch bkr_good_log"
        rlRun "touch bkr_bad_log"
        rlRun "touch bkr_weird_log"
        rlRun "touch bkr_skip_log"

        # This will create more subresults for each tmt-report-result call
        rlRun "tmt-report-result -o bkr_good_log extra-tmt-report-result/good PASS"
        rlRun "tmt-report-result -o bkr_bad_log extra-tmt-report-result/bad FAIL"
        rlRun "tmt-report-result -o bkr_weird_log extra-tmt-report-result/weird WARN"
        rlRun "tmt-report-result -o bkr_skip_log extra-tmt-report-result/skip SKIP"
    rlPhaseEnd

    rlPhaseStartCleanup "phase-cleanup"
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
