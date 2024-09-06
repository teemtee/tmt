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

        # Check the parent test outcomes
        rlAssertGrep "fail /test/beakerlib (on default-0)" "output"
        rlAssertGrep "fail /test/fail (on default-0)" "output"
        rlAssertGrep "pass /test/pass (on default-0)" "output"
        rlAssertGrep "total: 1 test passed and 2 tests failed" "output"

        # Check subtests outcomes

        ## The internal tests which are checking the TESTID and
        ## BEAKERLIB_COMMAND_REPORT_RESULT variables must pass
        rlAssertGrep "pass /test/beakerlib/Internal-test-of-environment-variable-values" "output"

        rlAssertGrep "pass /test/beakerlib/phase-setup" "output"
        rlAssertGrep "pass /test/beakerlib/phase-test-pass" "output"
        rlAssertGrep "fail /test/beakerlib/phase-test-fail" "output"
        rlAssertGrep "pass /test/beakerlib/phase-cleanup" "output"

        rlAssertGrep "warn /test/fail/subtest/weird" "output"
        rlAssertGrep "pass /test/pass/subtest/good2" "output"

        # Check the subresults get correctly saved in results.yaml
        rlRun "results_file=${run_dir}/plan/execute/results.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/beakerlib\") | .subresult' ${results_file} > subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/phase-setup" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/phase-test-pass" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/phase-test-fail" "subresults_beakerlib.yaml"
        rlAssertGrep "name: /test/beakerlib/phase-cleanup" "subresults_beakerlib.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/fail\") | .subresult' ${results_file} > subresults_fail.yaml"
        rlAssertGrep "name: /test/fail/subtest/good" "subresults_fail.yaml"
        rlAssertGrep "name: /test/fail/subtest/fail" "subresults_fail.yaml"
        rlAssertGrep "name: /test/fail/subtest/weird" "subresults_fail.yaml"

        rlRun "yq -ey '.[] | select(.name == \"/test/pass\") | .subresult' ${results_file} > subresults_pass.yaml"
        rlAssertGrep "name: /test/pass/subtest/good0" "subresults_pass.yaml"
        rlAssertGrep "name: /test/pass/subtest/good1" "subresults_pass.yaml"
        rlAssertGrep "name: /test/pass/subtest/good2" "subresults_pass.yaml"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm output"
        rlRun "rm subresults_{beakerlib,fail,pass}.yaml"
        rlRun "popd"
        rlRun "rm -rf $run_dir" 0 "Remove run directory"
    rlPhaseEnd

rlJournalEnd
