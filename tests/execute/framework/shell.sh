#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd shell"
        rlRun "set -o pipefail"
        rlRun "run=\$(mktemp -d)" 0 "Creating run directory/id"
        rlRun "results=$run/plans/execute/results.yaml"
    rlPhaseEnd

    function assert_check_result () {
        comment="$1"
        test="$2"
        check="$3"
        result="$4"
        rlAssertEquals "$comment" "$result" "$(yq -r ".[] | select(.name == \"$test\") | .check | .[] | select(.name == \"$check\") | .result" $results)"
    }

    tmt_command="LANG=en_US.UTF-8 tmt run --scratch -a --id ${run} provision --how local execute -vv report -vvv test --name"
    extract_results_command="yq -er '.[] | \"\\(.name) \\(.\"serial-number\") \\(.result) \\(.guest.name)\"'"

    testName="/tests/success"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 0 "Testing shell success"
        rlAssertGrep "cmd: ./shell.sh 0" $rlRun_LOG
        rlAssertGrep "testing shell with exit code 0" $rlRun_LOG
        rlAssertGrep "pass /tests/success" $rlRun_LOG
        rlRun -s "${extract_results_command} ${run}/plans/execute/results.yaml"
        rlAssertGrep "/tests/success 1 pass default-0" $rlRun_LOG
    rlPhaseEnd

    testName="/tests/failure"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 1 "Testing shell failure"
        rlAssertGrep "cmd: ./shell.sh 1" $rlRun_LOG
        rlAssertGrep "testing shell with exit code 1" $rlRun_LOG
        rlAssertGrep "fail /tests/failure" $rlRun_LOG
        rlRun -s "${extract_results_command} ${run}/plans/execute/results.yaml"
        rlAssertGrep "/tests/failure 1 fail default-0" $rlRun_LOG
    rlPhaseEnd

    testName="/tests/error"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing shell error"
        rlAssertGrep "cmd: ./shell.sh 2" $rlRun_LOG
        rlAssertGrep "testing shell with exit code 2" $rlRun_LOG
        rlAssertGrep "errr /tests/error" $rlRun_LOG
        rlRun -s "${extract_results_command} ${run}/plans/execute/results.yaml"
        rlAssertGrep "/tests/error 1 error default-0" $rlRun_LOG
    rlPhaseEnd

    testName="/tests/pidlock"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing shell pid file lock error"
        rlAssertGrep "cmd: ./shell.sh 122" $rlRun_LOG
        rlAssertGrep "testing shell with exit code 122" $rlRun_LOG
        rlAssertGrep "warn: Test failed to manage its pidfile." $rlRun_LOG
        rlAssertGrep "errr /tests/pidlock" $rlRun_LOG
        rlAssertGrep "pidfile locking" $rlRun_LOG
        rlRun -s "${extract_results_command} ${run}/plans/execute/results.yaml"
        rlAssertGrep "/tests/pidlock 1 error default-0" $rlRun_LOG
        assert_check_result "Test results have failed invocation pidfile check" "$testName" "internal/invocation" "fail"
    rlPhaseEnd

    testName="/tests/timeout"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing shell timeout error"
        rlAssertGrep "cmd: ./shell.sh 124" $rlRun_LOG
        rlAssertGrep "testing shell with exit code 124" $rlRun_LOG
        rlAssertGrep "errr /tests/timeout" $rlRun_LOG
        rlAssertGrep "timeout" $rlRun_LOG
        rlAssertGrep "Maximum test time '5m' exceeded." $rlRun_LOG
        rlAssertGrep "Adjust the test 'duration' attribute if necessary." $rlRun_LOG
        rlRun -s "${extract_results_command} ${run}/plans/execute/results.yaml"
        rlAssertGrep "/tests/timeout 1 error default-0" $rlRun_LOG
        assert_check_result "Test results have failed timeout check" "$testName" "internal/timeout" "fail"
    rlPhaseEnd

    testName="/tests/notfound"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing shell file not found error"
        rlAssertGrep "cmd: ./nosuchfile.sh" $rlRun_LOG
        rlAssertGrep "./nosuchfile.sh: No such file or directory" $rlRun_LOG
        rlAssertGrep "errr /tests/notfound" $rlRun_LOG
        rlRun -s "${extract_results_command} ${run}/plans/execute/results.yaml"
        rlAssertGrep "/tests/notfound 1 error default-0" $rlRun_LOG
    rlPhaseEnd

    testName="/tests/notexec"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing shell file not executable error"
        rlAssertGrep "cmd: /dev/null" $rlRun_LOG
        rlAssertGrep "/dev/null: Permission denied" $rlRun_LOG
        rlAssertGrep "errr /tests/notexec" $rlRun_LOG
        rlRun -s "${extract_results_command} ${run}/plans/execute/results.yaml"
        rlAssertGrep "/tests/notexec 1 error default-0" $rlRun_LOG
        assert_check_result "Test results have failed permission check" "$testName" "internal/permission" "fail"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r ${run}" 0 "Remove run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
