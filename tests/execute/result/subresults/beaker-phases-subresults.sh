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

        rlRun "[[ \$BEAKERLIB_COMMAND_REPORT_RESULT =~ rhts-report-result$ ]]" 0 "Check the variable contains path to a rhts-report-result script"
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
        rlRun "touch bkr_{good,bad,weird,skip,rhts_bad}_log"

        # This will create more subresults for each tmt-report-result call
        rlRun "tmt-report-result -o bkr_good_log extra-tmt-report-result/good PASS"
        rlRun "tmt-report-result -o bkr_bad_log extra-tmt-report-result/bad FAIL"
        rlRun "tmt-report-result -o bkr_weird_log extra-tmt-report-result/weird WARN"
        rlRun "tmt-report-result -o bkr_skip_log extra-tmt-report-result/skip SKIP"

        # We also support reporting the subresult via rhts-report-result alias
        rlRun "rhts-report-result extra-rhts-report-result/bad FAIL bkr_rhts_bad_log"
    rlPhaseEnd

    rlPhaseStartCleanup "phase-cleanup"
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
