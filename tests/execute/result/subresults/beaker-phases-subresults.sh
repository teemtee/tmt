#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1


rlJournalStart
    rlPhaseStartSetup "phase-setup"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Internal test of environment variable values"
        rlRun "test -n \"\$TMT_TEST_SERIAL_NUMBER\" -o -n \"\$TESTID\"" 0 "Check the variables are not empty"
        rlAssertEquals "TESTID must be set to TMT_TEST_SERIAL_NUMBER" "$TESTID" "$TMT_TEST_SERIAL_NUMBER"

        rlRun "[[ \$BEAKERLIB_COMMAND_REPORT_RESULT =~ tmt-report-result$ ]]" 0 "Check the variable contains path to a tmt-report-result script"
    rlPhaseEnd

    rlPhaseStartTest "phase-test pass"
        rlRun "echo mytest-pass | tee output" 0 "Check output"
        rlAssertGrep "mytest-pass" "output"
    rlPhaseEnd

    rlPhaseStartTest "phase-test fail"
        rlRun "echo mytest-fail | tee output" 0 "Check output"
        rlAssertGrep "asdf-asdf" "output"
    rlPhaseEnd

    rlPhaseStartTest "phase-test multiple tmt-report-result"
        rlRun "touch /tmp/bkr_good_log"
        rlRun "touch /tmp/bkr_bad_log"
        rlRun "touch /tmp/bkr_weird_log"
        rlRun "touch /tmp/bkr_skip_log"

        # This will create more subresults for each tmt-report-result call
        rlRun "tmt-report-result extra-tmt-report-result/good PASS /tmp/bkr_good_log"
        rlRun "tmt-report-result extra-tmt-report-result/bad FAIL /tmp/bkr_bad_log"
        rlRun "tmt-report-result extra-tmt-report-result/weird WARN /tmp/bkr_weird_log"
        rlRun "tmt-report-result extra-tmt-report-result/skip SKIP /tmp/bkr_skip_log"
    rlPhaseEnd

    rlPhaseStartCleanup "phase-cleanup"
        rlRun "popd"
        rlRun "rm -f /tmp/bkr_{good,bad,weird}_log"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
