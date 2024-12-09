#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1


rlJournalStart
    rlPhaseStartSetup
        rlRun "run_dir=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd subresults"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Test the subresults were generated into the results.yaml"
        rlRun -s "tmt run --id $run_dir --scratch -v 2>&1 >/dev/null" 1

        # Check the main result outcomes
        rlAssertGrep "fail /test/beakerlib (on default-0)" "$rlRun_LOG"
        rlAssertGrep "fail /test/shell/fail (on default-0)" "$rlRun_LOG"
        rlAssertGrep "pass /test/shell/pass (on default-0)" "$rlRun_LOG"
        rlAssertGrep "pass /test/shell/skip (on default-0)" "$rlRun_LOG"
        rlAssertGrep "total: 2 tests passed and 2 tests failed" "$rlRun_LOG"


        # Check the beakerlib test framework subtests outcomes

        ## The internal tests which are checking the TESTID and
        ## BEAKERLIB_COMMAND_REPORT_RESULT variables must pass
        rlAssertGrep "pass /Internal-test-of-environment-variable-values" "$rlRun_LOG"

        rlAssertGrep "pass /phase-setup" "$rlRun_LOG"
        rlAssertGrep "pass /phase-test-pass" "$rlRun_LOG"
        rlAssertGrep "fail /phase-test-fail" "$rlRun_LOG"
        rlAssertGrep "pass /phase-cleanup" "$rlRun_LOG"

        # Extra calls of tmt-report-result in the beakerlib test phase
        rlAssertGrep "pass /extra-tmt-report-result/good" "$rlRun_LOG"
        rlAssertGrep "fail /extra-tmt-report-result/bad" "$rlRun_LOG"
        rlAssertGrep "warn /extra-tmt-report-result/weird" "$rlRun_LOG"
        rlAssertGrep "skip /extra-tmt-report-result/skip" "$rlRun_LOG"

        # Extra call of rhts-report-result in the beakerlib test phase
        rlAssertGrep "fail /extra-rhts-report-result/bad" "$rlRun_LOG"

        # The phase itself must also exists as a subresult and it should pass,
        # even one or more of its extra {tmt,rhts}-report-result reported a
        # FAIL. The phase outcome evaluation is based on beakerlib test
        # framework.
        rlAssertGrep "pass /phase-test-multiple-tmt-report-result" "$rlRun_LOG"

        # Check the shell framework subtests outcomes
        rlAssertGrep "pass /pass-subtest/good0" "$rlRun_LOG"
        rlAssertGrep "pass /pass-subtest/good1" "$rlRun_LOG"
        rlAssertGrep "pass /pass-subtest/good2" "$rlRun_LOG"
        rlAssertGrep "pass /pass-subtest/good3" "$rlRun_LOG"

        rlAssertGrep "pass /skip-subtest/extra-pass" "$rlRun_LOG"
        rlAssertGrep "skip /skip-subtest/extra-skip1" "$rlRun_LOG"
        rlAssertGrep "skip /skip-subtest/extra-skip2" "$rlRun_LOG"

        rlAssertGrep "pass /fail-subtest/good" "$rlRun_LOG"
        rlAssertGrep "fail /fail-subtest/fail" "$rlRun_LOG"
        rlAssertGrep "warn /fail-subtest/weird" "$rlRun_LOG"
        rlAssertGrep "skip /fail-subtest/skip" "$rlRun_LOG"
        rlAssertGrep "fail /fail-subtest/fail-rhts" "$rlRun_LOG"


        # Check the subresults get correctly saved in results.yaml
        rlRun "results_file=${run_dir}/plan/execute/results.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/shell/pass\") | .subresult' ${results_file} > subresults_pass.yaml"
        rlAssertGrep "name: /pass-subtest/good0" "subresults_pass.yaml"
        rlAssertGrep "name: /pass-subtest/good1" "subresults_pass.yaml"
        rlAssertGrep "name: /pass-subtest/good2" "subresults_pass.yaml"
        rlAssertGrep "name: /pass-subtest/good3" "subresults_pass.yaml"
        rlAssertNotGrep "original-result: \(fail\|skip\|warn\)" "subresults_pass.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/shell/skip\") | .subresult' ${results_file} > subresults_skip.yaml"
        rlAssertGrep "name: /skip-subtest/extra-pass" "subresults_skip.yaml"
        rlAssertGrep "name: /skip-subtest/extra-skip1" "subresults_skip.yaml"
        rlAssertGrep "name: /skip-subtest/extra-skip2" "subresults_skip.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/shell/fail\") | .subresult' ${results_file} > subresults_fail.yaml"
        rlAssertGrep "name: /fail-subtest/good" "subresults_fail.yaml"
        rlAssertGrep "name: /fail-subtest/fail" "subresults_fail.yaml"
        rlAssertGrep "name: /fail-subtest/weird" "subresults_fail.yaml"
        rlAssertGrep "name: /fail-subtest/skip" "subresults_fail.yaml"
        rlAssertGrep "name: /fail-subtest/fail-rhts" "subresults_fail.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/beakerlib\") | .subresult' ${results_file} > subresults_beakerlib.yaml"
        rlAssertGrep "name: /phase-setup" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /phase-test-pass" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /phase-test-fail" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /phase-cleanup" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /extra-tmt-report-result/good" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /extra-tmt-report-result/bad" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /extra-tmt-report-result/weird" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /extra-tmt-report-result/skip" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /extra-rhts-report-result/bad" "subresults_beakerlib.yaml"


        # Check the subresults log entries are set in results.yaml
        rlAssertGrep "- data/.*/extra-tmt-report-result_good_bkr_good_log$" "subresults_beakerlib.yaml"
        rlAssertGrep "- data/.*/extra-tmt-report-result_bad_bkr_bad_log$" "subresults_beakerlib.yaml"
        rlAssertGrep "- data/.*/extra-tmt-report-result_weird_bkr_weird_log$" "subresults_beakerlib.yaml"
        rlAssertGrep "- data/.*/extra-tmt-report-result_skip_bkr_skip_log$" "subresults_beakerlib.yaml"
        rlAssertGrep "- data/.*/extra-rhts-report-result_bad_bkr_rhts_bad_log$" "subresults_beakerlib.yaml"

        rlAssertGrep "- data/.*/fail-subtest_good_good_log$" "subresults_fail.yaml"
        rlAssertGrep "- data/.*/fail-subtest_fail_fail_log$" "subresults_fail.yaml"
        rlAssertGrep "- data/.*/fail-subtest_weird_weird_log$" "subresults_fail.yaml"
        rlAssertGrep "- data/.*/fail-subtest_skip_skip_log$" "subresults_fail.yaml"
        rlAssertGrep "- data/.*/fail-subtest_fail-rhts_fail-rhts_log$" "subresults_fail.yaml"

        rlAssertGrep "- data/.*/skip-subtest_extra-skip2_skip-rhts_log$" "subresults_skip.yaml"

        rlAssertGrep "- data/.*/pass-subtest_good0_good0_log$" "subresults_pass.yaml"
        rlAssertGrep "- data/.*/pass-subtest_good1_good1_log$" "subresults_pass.yaml"
        rlAssertGrep "- data/.*/pass-subtest_good2_good2_log$" "subresults_pass.yaml"
        rlAssertGrep "- data/.*/pass-subtest_good3_good3_log$" "subresults_pass.yaml"


        # Check the subresults log files actually exist
        rlRun "log_dir=$run_dir/plan/execute/data/guest/default-0/test"
        rlAssertExists "$log_dir/shell/pass-3/data/pass-subtest_good0_good0_log"
        rlAssertExists "$log_dir/shell/pass-3/data/pass-subtest_good1_good1_log"
        rlAssertExists "$log_dir/shell/pass-3/data/pass-subtest_good2_good2_log"
        rlAssertExists "$log_dir/shell/pass-3/data/pass-subtest_good3_good3_log"

        rlAssertExists "$log_dir/shell/fail-2/data/fail-subtest_fail_fail_log"
        rlAssertExists "$log_dir/shell/fail-2/data/fail-subtest_good_good_log"
        rlAssertExists "$log_dir/shell/fail-2/data/fail-subtest_skip_skip_log"
        rlAssertExists "$log_dir/shell/fail-2/data/fail-subtest_weird_weird_log"
        rlAssertExists "$log_dir/shell/fail-2/data/fail-subtest_fail-rhts_fail-rhts_log"

        rlAssertExists "$log_dir/beakerlib-1/data/extra-tmt-report-result_bad_bkr_bad_log"
        rlAssertExists "$log_dir/beakerlib-1/data/extra-tmt-report-result_good_bkr_good_log"
        rlAssertExists "$log_dir/beakerlib-1/data/extra-tmt-report-result_skip_bkr_skip_log"
        rlAssertExists "$log_dir/beakerlib-1/data/extra-tmt-report-result_weird_bkr_weird_log"
        rlAssertExists "$log_dir/beakerlib-1/data/extra-rhts-report-result_bad_bkr_rhts_bad_log"
        rlAssertExists "$log_dir/beakerlib-1/data/journal.xml"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm subresults_{beakerlib,fail,pass,skip}.yaml"
        rlRun "popd"
        rlRun "rm -rf $run_dir" 0 "Remove run directory"
    rlPhaseEnd

rlJournalEnd
