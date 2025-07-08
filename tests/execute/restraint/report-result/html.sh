#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
    rlPhaseEnd

    rlPhaseStartTest "Verify html report represents all results"
        rlRun -s "tmt run -av --scratch --id $tmp report --how html" 1

        # Path of the generated file should be shown and the page should exist
        rlAssertGrep "output: .*/index.html" "$rlRun_LOG"
        HTML=$(grep "output:" "$rlRun_LOG" | sed 's/.*output: //')
        rlAssertExists "$HTML" || rlDie "Report file '$HTML' not found, nothing to check."
        rlAssertGrep "<html>" "$HTML" || rlDie "HTML file appears to be malformed."

        for result in "pass" "fail" "info" "warn" "error" "skip"; do
            # make sure results td exist for each
            rlAssertGrep "#results td.${result}" "$HTML"
            # make sure filter check boxes exist for each
            rlAssertGrep "<td><label><input type=\"checkbox\" id=\"filter_${result}\" onclick=\"filter_checkbox(this);\" checked>${result}</label></td>" "$HTML" -F

            if [ $result == "fail" ]; then
                check_tests=(
                    "/multi_reports/rhts-bad"
                    "/multi_reports/rstrnt-bad"
                    "/output/single"
                    "/report"
                    "/smoke/rhts-bad"
                    "/smoke/rstrnt-bad"
                    "/output/separate/bad-no-log"
                    "/output/separate/bad-with-log"
                    "/separate/separate_rhts_fail/test/bad"
                    "/separate/separate_rstrnt_fail/test/bad"
                )
            elif [ $result == "pass" ]; then
                check_tests=(
                    "/multi_reports/rhts-good"
                    "/multi_reports/rstrnt-good"
                    "/multi_reports/rhts-skip"
                    "/multi_reports/rstrnt-skip"
                    "/smoke/rhts-good"
                    "/smoke/rstrnt-good"
                    "/output/separate/good-no-log"
                    "/output/separate/good-with-log"
                    "/separate/separate_rhts_fail/test/good"
                    "/separate/separate_rhts_pass/test/good_1"
                    "/separate/separate_rhts_pass/test/good_2"
                    "/separate/separate_rhts_pass/test/good_3"
                    "/separate/separate_rstrnt_fail/test/good"
                    "/separate/separate_rstrnt_pass/test/good_1"
                    "/separate/separate_rstrnt_pass/test/good_2"
                    "/separate/separate_rstrnt_pass/test/good_3"
                )
            elif [ $result == "warn" ]; then
                check_tests=(
                    "/multi_reports/rhts-warn"
                    "/multi_reports/rstrnt-warn"
                    "/smoke/rhts-warn"
                    "/smoke/rstrnt-warn"
                    "/separate/separate_rhts_fail/test/weird"
                    "/separate/separate_rstrnt_fail/test/weird"
                )
            elif [ $result == "skip" ]; then
                check_tests=(
                    "/smoke/rhts-skip"
                    "/smoke/rstrnt-skip"
                    "/separate/separate_rhts_skip/test/skip_1"
                    "/separate/separate_rhts_skip/test/skip_2"
                    "/separate/separate_rhts_skip/test/skip_3"
                    "/separate/separate_rstrnt_skip/test/skip_1"
                    "/separate/separate_rstrnt_skip/test/skip_2"
                    "/separate/separate_rstrnt_skip/test/skip_3"
                )
            else
                check_tests=()
            fi

            for test_name in "${check_tests[@]}"; do
                test_name_suffix=$(basename "$test_name")
                # verify each test is listed with the proper result
                grep -B 1 "$test_name</td>" "$HTML" | tee "$tmp/$test_name_suffix"
                rlAssertGrep "class=\"result $result\">$result</td>" "$tmp/$test_name_suffix" -F
            done
        done
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp"
    rlPhaseEnd
rlJournalEnd
