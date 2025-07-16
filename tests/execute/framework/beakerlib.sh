#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd beakerlib"
        rlRun "set -o pipefail"
        rlRun "run=\$(mktemp -d)" 0 "Creating run directory/id"
        rlRun "results=$run/plans/execute/results.yaml"
    rlPhaseEnd

    function assert_result () {
        name="$1"
        serial="$2"
        result="$3"
        guest="$4"
        note="$5"
        actual=$(yq -er ".[] | \"\\(.name) \\(.\"serial-number\") \\(.result) \\(.guest.name) \\(if .note == [] then \"\" else ((.note[] | select(. == \"$note\")) // \"\") end)\"" "$results")
        rlAssertEquals "Check result for $name" "$actual" "$name $serial $result $guest $note"
    }

    function assert_check_result () {
        comment="$1"
        test="$2"
        check="$3"
        result="$4"
        rlAssertEquals "$comment" "$result" "$(yq -r ".[] | select(.name == \"$test\") | .check | .[] | select(.name == \"$check\") | .result" $results)"
    }

    tmt_command="tmt run --scratch -a --id ${run} provision --how local execute -vv report -vvv test --name"

    testName="/tests/pass"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 0 "Testing beakerlib success"
        # tmt sent the correct command
        rlAssertGrep "cmd: ./pass.sh" $rlRun_LOG
        # beakerlib results as expected
        rlAssertGrep "OVERALL RESULT: PASS (/tests/pass)" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "pass /tests/pass" $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/pass" "1" "pass" "default-0" ""
    rlPhaseEnd

    testName="/tests/fail"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 1 "Testing beakerlib failure"
        # tmt sent the correct command
        rlAssertGrep "cmd: ./fail.sh" $rlRun_LOG
        # beakerlib results as expected
        rlAssertGrep "OVERALL RESULT: FAIL (/tests/fail)" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "fail /tests/fail" $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/fail" "1" "fail" "default-0" ""
    rlPhaseEnd

    testName="/tests/warn"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 1 "Testing beakerlib warning"
        # tmt sent the correct command
        rlAssertGrep "cmd: ./warn.sh" $rlRun_LOG
        # beakerlib results as expected
        rlAssertGrep "OVERALL RESULT: WARN (/tests/warn)" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "warn /tests/warn" $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/warn" "1" "warn" "default-0" ""
    rlPhaseEnd

    testName="/tests/worst"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 1 "Testing beakerlib picking the worst out of multiple outcomes"
        # tmt sent the correct command
        rlAssertGrep "cmd: ./worst.sh" $rlRun_LOG
        # beakerlib results as expected
        rlAssertGrep "RESULT: WARN (Setup)" $rlRun_LOG
        rlAssertGrep "RESULT: PASS (Test)" $rlRun_LOG
        rlAssertGrep "RESULT: FAIL (Test)" $rlRun_LOG
        rlAssertGrep "RESULT: WARN (Cleanup)" $rlRun_LOG
        rlAssertGrep "OVERALL RESULT: FAIL (/tests/worst)" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "fail /tests/worst" $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/worst" "1" "fail" "default-0" ""
    rlPhaseEnd

    testName="/tests/timeout"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing beakerlib timeout"
        # tmt sent the correct command
        rlAssertGrep "cmd: ./timeout.sh" $rlRun_LOG
        # beakerlib results as expected
        rlAssertGrep "Running 'exit 124'" $rlRun_LOG
        rlAssertNotGrep "OVERALL RESULT" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "errr /tests/timeout" $rlRun_LOG
        rlAssertGrep "timeout" $rlRun_LOG
        rlAssertGrep "Maximum test time '5m' exceeded." $rlRun_LOG
        rlAssertGrep "Adjust the test 'duration' attribute if necessary." $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/timeout" "1" "error" "default-0" ""
        assert_check_result "Test results have failed timeout check" "$testName" "internal/timeout" "fail"
    rlPhaseEnd

    testName="/tests/pidlock"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing beakerlib pidlock"
        # tmt sent the correct command
        rlAssertGrep "cmd: ./pidlock.sh" $rlRun_LOG
        # beakerlib results as expected
        rlAssertGrep "Running 'exit 122'" $rlRun_LOG
        rlAssertNotGrep "OVERALL RESULT" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "errr /tests/pidlock" $rlRun_LOG
        rlAssertGrep "pidfile locking" $rlRun_LOG
        rlAssertGrep "warn: Test failed to manage its pidfile." $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/pidlock" "1" "error" "default-0" ""
        assert_check_result "Test results have failed invocation pidfile check" "$testName" "internal/invocation" "fail"
    rlPhaseEnd

    testName="/tests/incomplete-fail"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing beakerlib incomplete while failing"
        # tmt sent the correct command
        rlAssertGrep "cmd: ./incomplete-fail.sh" $rlRun_LOG
        # beakerlib results as expected
        rlAssertGrep "RESULT: FAIL (Test)" $rlRun_LOG
        rlAssertGrep "Running 'exit 0'" $rlRun_LOG
        rlAssertNotGrep "OVERALL RESULT" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "errr /tests/incomplete-fail" $rlRun_LOG
        rlAssertGrep "beakerlib: State 'incomplete'" $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/incomplete-fail" "1" "error" "default-0" "beakerlib: State 'incomplete'"
    rlPhaseEnd

    testName="/tests/incomplete-pass"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing beakerlib incomplete while passing"
        # tmt sent the correct command
        rlAssertGrep "cmd: ./incomplete-pass.sh" $rlRun_LOG
        # beakerlib results as expected
        rlAssertGrep "RESULT: PASS (Test)" $rlRun_LOG
        rlAssertGrep "Running 'exit 0'" $rlRun_LOG
        rlAssertNotGrep "OVERALL RESULT" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "errr /tests/incomplete-pass" $rlRun_LOG
        rlAssertGrep "beakerlib: State 'incomplete'" $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/incomplete-pass" "1" "error" "default-0" "beakerlib: State 'incomplete'"
    rlPhaseEnd

    testName="/tests/notfound"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing beakerlib file not found"
        # tmt sent the correct command
        rlAssertGrep "cmd: ./nosuchfile.sh" $rlRun_LOG
        # beakerlib results as expected
        rlAssertNotGrep "RESULT" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "errr /tests/notfound" $rlRun_LOG
        rlAssertGrep "beakerlib: TestResults FileError" $rlRun_LOG
        rlAssertGrep "No such file or directory" $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/notfound" "1" "error" "default-0" "beakerlib: TestResults FileError"
    rlPhaseEnd

    testName="/tests/notexec"
    rlPhaseStartTest "${testName}"
        rlRun -s "${tmt_command} ${testName} >/dev/null" 2 "Testing beakerlib file permission denied"
        # tmt sent the correct command
        rlAssertGrep "cmd: /dev/null" $rlRun_LOG
        # beakerlib results as expected
        rlAssertNotGrep "RESULT" $rlRun_LOG
        # tmt prints the correct result into log
        rlAssertGrep "errr /tests/notexec" $rlRun_LOG
        rlAssertGrep "beakerlib: TestResults FileError" $rlRun_LOG
        rlAssertGrep "Permission denied" $rlRun_LOG
        # tmt saves the correct results, including note, into results yaml
        assert_result "/tests/notexec" "1" "error" "default-0" "beakerlib: TestResults FileError"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r ${run}" 0 "Remove run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
