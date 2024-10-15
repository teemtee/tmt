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
        rlRun "tmt run --id $run_dir --scratch -v 2>&1 >/dev/null | tee output" 1

        # Check the main result outcomes
        rlAssertGrep "fail /test/beakerlib (on default-0)" "output"
        rlAssertGrep "fail /test/fail (on default-0)" "output"
        rlAssertGrep "pass /test/pass (on default-0)" "output"
        rlAssertGrep "pass /test/skip (on default-0)" "output"
        rlAssertGrep "total: 2 tests passed and 2 tests failed" "output"


        # Check the beakerlib test framework subtests outcomes

        ## The internal tests which are checking the TESTID and
        ## BEAKERLIB_COMMAND_REPORT_RESULT variables must pass
        rlAssertGrep "pass /test/beakerlib/Internal-test-of-environment-variable-values" "output"

        rlAssertGrep "pass /test/beakerlib/phase-setup" "output"
        rlAssertGrep "pass /test/beakerlib/phase-test-pass" "output"
        rlAssertGrep "fail /test/beakerlib/phase-test-fail" "output"
        rlAssertGrep "pass /test/beakerlib/phase-cleanup" "output"

        # Extra calls of tmt-report-result in the beakerlib test phase
        rlAssertGrep "pass /test/beakerlib/extra-tmt-report-result/good" "output"
        rlAssertGrep "fail /test/beakerlib/extra-tmt-report-result/bad" "output"
        rlAssertGrep "warn /test/beakerlib/extra-tmt-report-result/weird" "output"
        rlAssertGrep "skip /test/beakerlib/extra-tmt-report-result/skip" "output"

        # The phase itself must also exists as a subresult and it should pass,
        # even one of its extra tmt-report-result reported a FAIL. The phase
        # outcome evaluation is based on beakerlib test framework.
        rlAssertGrep "pass /test/beakerlib/phase-test-multiple-tmt-report-result" "output"


        # Check the shell framework subtests outcomes
        rlAssertGrep "pass /test/fail/subtest/good" "output"
        rlAssertGrep "fail /test/fail/subtest/fail" "output"
        rlAssertGrep "warn /test/fail/subtest/weird" "output"
        rlAssertGrep "skip /test/fail/subtest/skip" "output"

        rlAssertGrep "pass /test/pass/subtest/good0" "output"
        rlAssertGrep "pass /test/pass/subtest/good1" "output"
        rlAssertGrep "pass /test/pass/subtest/good2" "output"

        rlAssertGrep "pass /test/skip/subtest/extra-pass" "output"
        rlAssertGrep "skip /test/skip/subtest/extra-skip" "output"


        # Check the subresults get correctly saved in results.yaml
        rlRun "results_file=${run_dir}/plan/execute/results.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/beakerlib\") | .subresult' ${results_file} > subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/phase-setup" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/phase-test-pass" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/phase-test-fail" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/phase-cleanup" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/extra-tmt-report-result/good" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/extra-tmt-report-result/bad" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/extra-tmt-report-result/weird" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/extra-tmt-report-result/skip" "subresults_beakerlib.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/fail\") | .subresult' ${results_file} > subresults_fail.yaml"
        rlAssertGrep "name: /test/fail/subtest/good" "subresults_fail.yaml"
        rlAssertGrep "name: /test/fail/subtest/fail" "subresults_fail.yaml"
        rlAssertGrep "name: /test/fail/subtest/weird" "subresults_fail.yaml"
        rlAssertGrep "name: /test/fail/subtest/skip" "subresults_fail.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/pass\") | .subresult' ${results_file} > subresults_pass.yaml"
        rlAssertGrep "name: /test/pass/subtest/good0" "subresults_pass.yaml"
        rlAssertGrep "name: /test/pass/subtest/good1" "subresults_pass.yaml"
        rlAssertGrep "name: /test/pass/subtest/good2" "subresults_pass.yaml"
        rlAssertNotGrep "original-result: \(fail\|skip\|warn\)" "subresults_pass.yaml"

        # Check the subresults log entries are set in results.yaml
        rlAssertGrep "- extra-tmt-report-result_good_bkr_good_log" "subresults_beakerlib.yaml"
        rlAssertGrep "- extra-tmt-report-result_bad_bkr_bad_log" "subresults_beakerlib.yaml"
        rlAssertGrep "- extra-tmt-report-result_weird_bkr_weird_log" "subresults_beakerlib.yaml"
        rlAssertGrep "- extra-tmt-report-result_skip_bkr_skip_log" "subresults_beakerlib.yaml"

        rlAssertGrep "- subtest_good_good_log" "subresults_fail.yaml"
        rlAssertGrep "- subtest_fail_fail_log" "subresults_fail.yaml"
        rlAssertGrep "- subtest_weird_weird_log" "subresults_fail.yaml"
        rlAssertGrep "- subtest_skip_skip_log" "subresults_fail.yaml"

        rlAssertGrep "- subtest_good0_good0_log" "subresults_pass.yaml"
        rlAssertGrep "- subtest_good1_good1_log" "subresults_pass.yaml"
        rlAssertGrep "- subtest_good2_good2_log" "subresults_pass.yaml"

        # Check the subresults log files actually exist
        rlRun "log_dir=$run_dir/plan/execute/data/guest/default-0/test"
        rlAssertExists "$log_dir/pass-3/data/subtest_good0_good0_log"
        rlAssertExists "$log_dir/pass-3/data/subtest_good1_good1_log"
        rlAssertExists "$log_dir/pass-3/data/subtest_good2_good2_log"

        rlAssertExists "$log_dir/fail-2/data/subtest_fail_fail_log"
        rlAssertExists "$log_dir/fail-2/data/subtest_good_good_log"
        rlAssertExists "$log_dir/fail-2/data/subtest_skip_skip_log"
        rlAssertExists "$log_dir/fail-2/data/subtest_weird_weird_log"

        rlAssertExists "$log_dir/beakerlib-1/data/extra-tmt-report-result_bad_bkr_bad_log"
        rlAssertExists "$log_dir/beakerlib-1/data/extra-tmt-report-result_good_bkr_good_log"
        rlAssertExists "$log_dir/beakerlib-1/data/extra-tmt-report-result_skip_bkr_skip_log"
        rlAssertExists "$log_dir/beakerlib-1/data/extra-tmt-report-result_weird_bkr_weird_log"
        rlAssertExists "$log_dir/beakerlib-1/data/journal.xml"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm output"
        rlRun "rm subresults_{beakerlib,fail,pass}.yaml"
        rlRun "popd"
        rlRun "rm -rf $run_dir" 0 "Remove run directory"
    rlPhaseEnd

rlJournalEnd
