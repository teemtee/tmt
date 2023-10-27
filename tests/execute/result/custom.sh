#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd custom"
        rlRun "set -o pipefail"
        rlRun "run=\$(mktemp -d)" 0 "Creating run direcotory/id"
    rlPhaseEnd

    tmt_command="tmt run --scratch -a --id ${run} provision --how local execute -vv report -vv test --name"

    testName="/test/custom-results"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 1 "Test provides 'results.yaml' file by itself"
        rlAssertGrep "00:11:22 pass /test/custom-results/test/passing" $rlRun_LOG
        rlAssertGrep "00:22:33 fail /test/custom-results/test/failing" $rlRun_LOG
        rlAssertGrep "00:00:00 skip /test/custom-results/test/skipped" $rlRun_LOG
        # The duration of the main result is replaced with the duration measured by tmt for the whole test.
        rlAssertGrep "00:00:00 pass /test/custom-results (on default-0) \[1/1\]" $rlRun_LOG
        rlAssertGrep "00:55:44 pass /test/custom-results/without-leading-slash.*name should start with '/'" $rlRun_LOG
        rlAssertGrep "total: 3 tests passed, 1 test failed and 1 test skipped" $rlRun_LOG

        rlAssertExists "$(sed -n 's/ *pass_log: \(.\+\)/\1/p' $rlRun_LOG)"
        rlAssertExists "$(sed -n 's/ *fail_log: \(.\+\)/\1/p' $rlRun_LOG)"
        rlAssertExists "$(sed -n 's/ *another_log: \(.\+\)/\1/p' $rlRun_LOG)"
        rlAssertExists "$(sed -n 's/ *slash_log: \(.\+\)/\1/p' $rlRun_LOG)"

        rlRun -s "yq -er '.[] | \"\\(.name) \\(.\"serial-number\") \\(.result) \\(.guest.name)\"' $run/default/plan/execute/results.yaml"
        rlAssertGrep "/test/custom-results/test/passing 1 pass default-0" $rlRun_LOG
        rlAssertGrep "/test/custom-results/test/failing 1 fail default-0" $rlRun_LOG
        rlAssertGrep "/test/custom-results 1 pass default-0" $rlRun_LOG
        rlAssertGrep "/test/custom-results/without-leading-slash 1 pass default-0" $rlRun_LOG
    rlPhaseEnd

    testName="/test/custom-json-results"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 1 "Test provides 'results.json' file by itself"
        rlAssertGrep "00:12:23 pass /test/custom-json-results/test/passing" $rlRun_LOG
        rlAssertGrep "00:23:34 fail /test/custom-json-results/test/failing" $rlRun_LOG
        # The duration of the main result is replaced with the duration measured by tmt for the whole test.
        rlAssertGrep "00:00:00 pass /test/custom-json-results .* \[1/1\]" $rlRun_LOG
        rlAssertGrep "total: 2 tests passed and 1 test failed" $rlRun_LOG

        rlAssertExists "$(sed -n 's/ *pass_log: \(.\+\)/\1/p' $rlRun_LOG)"
        rlAssertExists "$(sed -n 's/ *fail_log: \(.\+\)/\1/p' $rlRun_LOG)"
        rlAssertExists "$(sed -n 's/ *another_log: \(.\+\)/\1/p' $rlRun_LOG)"
    rlPhaseEnd

    testName="/test/missing-custom-results"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 2 "Test does not provide 'results.yaml' file"
        rlAssertGrep "custom results file not found in '/tmp/.*/default/plan/execute/data/guest/default-0/test/missing-custom-results-1/data" $rlRun_LOG
    rlPhaseEnd

    testName="/test/empty-custom-results-file"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 2 "Test provides empty 'results.yaml' file"
        rlAssertGrep "custom results are empty" $rlRun_LOG
    rlPhaseEnd

    testName="/test/empty-custom-results-json"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 2 "Test provides empty 'results.json' file"
        rlAssertGrep "custom results are empty" $rlRun_LOG
    rlPhaseEnd

    testName="/test/wrong-yaml-results-file"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 2 "Test provides 'results.yaml' in valid YAML but wrong results format"
        rlAssertGrep "Expected list in yaml data, got 'dict'." $rlRun_LOG
    rlPhaseEnd

    testName="/test/wrong-json-results-file"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 2 "Test provides 'results.json' in valid JSON but wrong results format"
        rlAssertGrep "Expected list in json data, got 'dict'." $rlRun_LOG
    rlPhaseEnd

    testName="/test/invalid-yaml-results-file"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 2 "Test provides 'results.yaml' not in YAML format"
        rlAssertGrep "Invalid yaml syntax:" $rlRun_LOG
    rlPhaseEnd

    testName="/test/invalid-json-results-file"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 2 "Test provides 'results.json' not in JSON format"
        rlAssertGrep "Invalid json syntax:" $rlRun_LOG
    rlPhaseEnd

    testName="/test/wrong-yaml-content"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} 2>&1 >/dev/null" 2 "Test provides partial result with wrong value"
        rlAssertGrep "Invalid partial custom result 'errrrrr'." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r ${run}" 0 "Remove run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
