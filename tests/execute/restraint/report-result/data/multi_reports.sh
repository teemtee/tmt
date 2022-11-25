#!/bin/bash
TESTARGS=${TESTARGS:-"fail"}
REPORT=${REPORT:-"restraint"}

function report_result {
	if [ $REPORT == "rhts" ]; then
	    rhts-report-result "$1" "$2" "$OUTPUTFILE" "$3"
	else
	    rstrnt-report-result "$1" "$2" "$3"
	fi
}

phase_test()
{
    echo "Test phase: $1 Result: $2 Result Code: $3"
    report_result "$1" "$2" "$3"
}

case "${TESTARGS}" in
    "fail")
        phase_test "Regression test 1" "PASS" "0"
        phase_test "Regression test 2" "FAIL" "1"
        phase_test "Regression test 3" "WARN" "2"
        phase_test "Regression test 4" "SKIP" "1"
        phase_test "Regression test 5" "PASS" "0"
        ;;
    "pass")
        phase_test "Regression test 1" "PASS" "0"
        phase_test "Regression test 2" "PASS" "0"
        phase_test "Regression test 3" "PASS" "0"
        phase_test "Regression test 4" "PASS" "0"
        phase_test "Regression test 5" "PASS" "0"
        ;;
    "skip")
        phase_test "Regression test 1" "PASS" "0"
        phase_test "Regression test 2" "PASS" "0"
        phase_test "Regression test 3" "SKIP" "1"
        ;;
    "warn")
        phase_test "Regression test 1" "PASS" "0"
        phase_test "Regression test 2" "WARN" "1"
        phase_test "Regression test 3" "PASS" "0"
        ;;
    *)
        ;;
esac
