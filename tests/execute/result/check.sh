#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "pushd check"
        rlRun "set -o pipefail"
    rlPhaseEnd

    function test_result () {
        pattern="$1"
        extra_lines="$2"

        shift 2

        rlRun "grep -P -A$extra_lines \"\s+\d\d:\d\d:\d\d\s+$pattern\" $run/report.txt > $run/test.txt"
        rlRun "cat $run/test.txt"

        for i in `seq 1 $extra_lines`; do
            pattern="$1"
            shift

            rlRun "grep -P \"\s+$pattern\" $run/test.txt"
        done
    }

    rlPhaseStartTest "Check Results"
        rlRun "tmt run -av --id $run provision --how $PROVISION_HOW" 1
        rlRun -s "tmt run --id $run report -v" 1

        rlRun "mv $rlRun_LOG $run/report.txt"

        test_result "pass /test/check-fail-info" \
                    3 \
                    "Note: check 'dmesg' is informational" \
                    "pass dmesg \(before-test check\)" \
                    "fail dmesg \(after-test check\)"

        test_result "fail /test/check-fail-respect" \
                    4 \
                    "Note: check 'dmesg' failed" \
                    "Note: original test result: pass" \
                    "pass dmesg \(before-test check\)" \
                    "fail dmesg \(after-test check\)"

        test_result "pass /test/check-override" \
                    4 \
                    "Note: check 'dmesg' failed" \
                    "Note: test result overridden: pass" \
                    "pass dmesg \(before-test check\)" \
                    "fail dmesg \(after-test check\)"

        test_result "pass /test/check-pass" \
                    2 \
                    "pass dmesg \(before-test check\)" \
                    "pass dmesg \(after-test check\)"

        test_result "fail /test/check-pass-test-xfail" \
                    4 \
                    "Note: test was expected to fail" \
                    "Note: original test result: pass" \
                    "pass dmesg \(before-test check\)" \
                    "pass dmesg \(after-test check\)"

        test_result "pass /test/check-xfail-fail" \
                    3 \
                    "Note: check 'dmesg' failed as expected" \
                    "pass dmesg \(before-test check\)" \
                    "fail dmesg \(after-test check\)"

        test_result "fail /test/check-xfail-pass" \
                    4 \
                    "Note: check 'dmesg' did not fail as expected" \
                    "Note: original test result: pass" \
                    "pass dmesg \(before-test check\)" \
                    "pass dmesg \(after-test check\)"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
