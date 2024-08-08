#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

RESULT_FILE="$TMT_TEST_DATA/tmt-report-results.yaml"

rlJournalStart
    rlPhaseStartSetup
        rlRun "rm -f $RESULT_FILE" 0 "Report file successfully removed pre test."
	rlRun "touch /tmp/example_output.txt"
    rlPhaseEnd

    rlPhaseStartTest 'Verify mocked Restraint rstrnt-report-result file generated correctly.'
        rlRun "rstrnt-report-result --server http://test-example.com report SKIP" 0 "Generating Restraint report of skipped test."
        rlRun "ls $RESULT_FILE" 0 "Result report successfully generated."
        rlRun -s "cat $RESULT_FILE"
        rlAssertGrep 'result: skip' $rlRun_LOG
	rlRun "rm -f $RESULT_FILE" 0 "Result report successfully deleted."
        rlRun "rstrnt-report-result --server http://test-example.com --port 55 --disable-plugin avc --message 'Example output message.' -o /tmp/example_output.txt report PASS 66" 0 "Generating Restraint report of passed test."
        rlRun -s "cat $RESULT_FILE"
        rlAssertGrep "- report_example_output.txt" $rlRun_LOG
        rlAssertGrep 'name: /report' $rlRun_LOG
        rlAssertGrep 'result: pass' $rlRun_LOG
	rlRun "rm -f $RESULT_FILE" 0 "Result report successfully deleted."
        rlRun "rstrnt-report-result --server http://test-example.com report WARN" 0 "Generating Restraint report of warned test."
        rlRun -s "cat $RESULT_FILE"
        rlAssertGrep 'result: warn' $rlRun_LOG
	rlRun "rm -f $RESULT_FILE" 0 "Result report successfully deleted."
        rlRun "rstrnt-report-result --server http://test-example.com report FAIL" 0 "Generating Restraint report of failed test."
        rlRun -s "cat $RESULT_FILE"
        rlAssertGrep 'result: fail' $rlRun_LOG
	rlRun "rm -f $RESULT_FILE" 0 "Result report successfully deleted."
    rlPhaseEnd

    rlPhaseStartTest 'Verify mocked RHTS rhts-report-result file generated correctly.'
        rlRun "rhts-report-result rhts-report SKIP /tmp/example_output.txt" 0 "Generating RHTS report of skipped test without optional metric."
        rlRun "ls $RESULT_FILE" 0 "Result report successfully generated."
        rlRun -s "cat $RESULT_FILE"
        rlAssertGrep 'result: skip' $rlRun_LOG
	rlRun "rm -f $RESULT_FILE" 0 "Result report successfully deleted."
        rlRun "rhts-report-result rhts-report PASS /tmp/example_output.txt 66" 0 "Generating RHTS report of passed test."
        rlRun -s "cat $RESULT_FILE"
        rlAssertGrep "- rhts-report_example_output.txt" $rlRun_LOG
        rlAssertGrep 'name: /rhts-report' $rlRun_LOG
        rlAssertGrep 'result: pass' $rlRun_LOG
	rlRun "rm -f $RESULT_FILE" 0 "Result report successfully deleted."
        rlRun "rhts-report-result rhts-report WARN /tmp/example_output.txt 66" 0 "Generating RHTS report of warned test."
        rlRun -s "cat $RESULT_FILE"
        rlAssertGrep 'result: warn' $rlRun_LOG
	rlRun "rm -f $RESULT_FILE" 0 "Result report successfully deleted."
        rlRun "rhts-report-result rhts-report FAIL /tmp/example_output.txt 66" 0 "Generating RHTS report of failed test."
        rlRun -s "cat $RESULT_FILE"
        rlAssertGrep 'result: fail' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -f $RESULT_FILE" 0 "Report file successfully removed post test."
    rlPhaseEnd
rlJournalEnd
