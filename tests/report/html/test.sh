#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

PATH_INDEX="/plan/report/default-0/index.html"

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "run_dir=$tmp/original"
    rlPhaseEnd

    for option in "" "--absolute-paths"; do
        rlPhaseStartTest "Check status (${option:-relative paths})"
            rlRun -s "tmt run -av --scratch --id $run_dir report -h html $option 2>&1 >/dev/null | tee output" 2
            rlAssertGrep "summary: 3 tests passed, 1 test failed and 2 errors" $rlRun_LOG -F

            # Path of the generated file should be shown and the page should exist
            rlAssertGrep "output: .*/index.html" $rlRun_LOG
            HTML=$(grep "output:" $rlRun_LOG | sed 's/.*output: //')
            rlAssertExists "$HTML" || rlDie "Report file '$HTML' not found, nothing to check."

            test_name_suffix=error
            grep -B 1 "/test/$test_name_suffix</td>" $HTML | tee $tmp/$test_name_suffix
            rlAssertGrep 'class="result error">error</td>' $tmp/$test_name_suffix -F

            test_name_suffix=fail
            grep -B 1 "/test/$test_name_suffix</td>" $HTML | tee $tmp/$test_name_suffix
            rlAssertGrep 'class="result fail">fail</td>' $tmp/$test_name_suffix -F

            test_name_suffix=pass
            grep -B 1 "/test/$test_name_suffix</td>" $HTML | tee $tmp/$test_name_suffix
            rlAssertGrep 'class="result pass">pass</td>' $tmp/$test_name_suffix -F

            test_name_suffix=timeout
            grep -B 1 "/test/$test_name_suffix</td>" $HTML | tee $tmp/$test_name_suffix
            rlAssertGrep 'class="result error">error</td>' $tmp/$test_name_suffix -F
            sed -e "/name\">\/test\/$test_name_suffix/,/\/tr/!d" $HTML | tee $tmp/$test_name_suffix-note
            rlAssertGrep '<td class="note">timeout</td>' $tmp/$test_name_suffix-note -F

            test_name_suffix=xfail
            grep -B 1 "/test/$test_name_suffix</td>" $HTML | tee $tmp/$test_name_suffix
            rlAssertGrep 'class="result pass">pass</td>' $tmp/$test_name_suffix -F
            sed -e "/name\">\/test\/$test_name_suffix/,/\/tr/!d" $HTML | tee $tmp/$test_name_suffix-note
            rlAssertGrep '<td class="note">original result: fail</td>' $tmp/$test_name_suffix-note -F
        rlPhaseEnd

        if [ "$option" = "" ]; then
            rlPhaseStartTest "Check relative links"
                moved_dir="$tmp/moved"
                rlRun "mv $run_dir $moved_dir"
                rlRun "pushd $(dirname ${HTML/original/moved})"
                grep -Po '(?<=href=")[^"]+' "index.html" | while read f_path; do
                    [[ $f_path == /* ]] && rlFail "Path $f_path is not a relative path"
                    rlAssertExists $f_path
                done
                rlRun "popd"
            rlPhaseEnd
        else
            rlPhaseStartTest "Check absolute links"
                grep -Po '(?<=href=")[^"]+' "$HTML" | while read f_path; do
                    [[ $f_path == /* ]] || rlFail "Path $f_path is not an absolute path"
                    rlAssertExists $f_path
                done
            rlPhaseEnd
        fi
    done

    rlPhaseStartTest "Check guest display modes"
        # Two cases for multihost, one with a single guest, other with multiple, to test the default "auto"...
        rlRun -s "tmt run -av --scratch --id $tmp test -n pass report -h html"
        rlAssertNotGrep "<th>Guest</th>" "$tmp/plan/report/default-0/index.html"
        rlAssertNotGrep "<td class=\"guest\">default-0</td>" "$tmp/plan/report/default-0/index.html"

        rlRun -s "tmt -c report_multihost=yes run -av --scratch --id $tmp plan -n multihost-plan test -n pass report -h html"
        rlAssertGrep "<th>Guest</th>" "$tmp/multihost-plan/report/default-0/index.html"
        rlAssertGrep "<td class=\"guest\">guest-1</td>" "$tmp/multihost-plan/report/default-0/index.html"
        rlAssertGrep "<td class=\"guest\">guest-2</td>" "$tmp/multihost-plan/report/default-0/index.html"

        # ...then "always", ...
        rlRun -s "tmt run -av --scratch --id $tmp test -n pass report -h html --display-guest always"
        rlAssertGrep "<th>Guest</th>" "$tmp/plan/report/default-0/index.html"
        rlAssertGrep "<td class=\"guest\">default-0</td>" "$tmp/plan/report/default-0/index.html"

        # ... and "never".
        rlRun -s "tmt run -av --scratch --id $tmp test -n pass report -h html --display-guest never"
        rlAssertNotGrep "<th>Guest</th>" "$tmp/plan/report/default-0/index.html"
        rlAssertNotGrep "<td class=\"guest\">default-0</td>" "$tmp/plan/report/default-0/index.html"
    rlPhaseEnd


    # Subresults phase with faked results.yaml data
    rlPhaseStartTest "Check the subresults and their checks"
        rlRun -s "tmt run -av --scratch --id $tmp plan -n plan test -n subresults report -h html"
        rlRun "cp -r faked-subresults-results.yaml $tmp/plan/execute/results.yaml" 0 "Faking the execute/results.yaml with subresult data"
        rlRun -s "tmt run --last --id $tmp plan -n plan test -n subresult report -h html -v"

        # Subresults and their checks
        rlAssertGrep '<td class="name">/test/subresults</td>' "$tmp/plan/report/default-0/index.html"
        rlAssertGrep 'subresults&nbsp;\[[+]\]</button>' "$tmp/plan/report/default-0/index.html"
        rlAssertGrep '<h3>Subresults</h3>' "$tmp/plan/report/default-0/index.html"
        rlAssertGrep '<td class="name">/test/subresults/good</td>' "$tmp/plan/report/default-0/index.html"
        rlAssertGrep '<td class="name">/test/subresults/fail</td>' "$tmp/plan/report/default-0/index.html"
        rlAssertGrep '<tr class="subresult-check" id="subresult-check-3">' "$tmp/plan/report/default-0/index.html"
        rlAssertGrep '<td class="name">dmesg (before-test)</td>' "$tmp/plan/report/default-0/index.html"

        # Global result checks
        rlAssertGrep 'checks&nbsp;\[[+]\]</button>' "$tmp/plan/report/default-0/index.html"
        rlAssertGrep '<td class="name">avc (before-test)</td>' "$tmp/plan/report/default-0/index.html"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm output"
        rlRun "popd"
        rlRun "rm -rf $tmp"
    rlPhaseEnd
rlJournalEnd
