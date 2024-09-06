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

    rlPhaseStartCleanup "phase-cleanup"
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
