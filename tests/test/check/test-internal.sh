#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    comment="$1"
    test="$2"
    check="$3"
    result="$4"
    rlAssertEquals "$comment" "$result" "$(yq -r ".[] | select(.name == \"$test\") | .check | .[] | select(.name == \"$check\") | .result" $results)"
}

function assert_no_check_results () {
    comment="$1"
    test="$2"
    rlRun "yq -r '.[] | select(.name == \"$test\") | .check | length == 0' $results" 0 "$comment"
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "results=$run/plan/execute/results.yaml"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    tmt_command="tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n"
    rlPhaseStartTest "Passing test with $PROVISION_HOW"
        rlRun "$tmt_command /internal/pass"
        assert_no_check_results "/internal/pass" "Test results have no checks"
    rlPhaseEnd

    rlPhaseStartTest "Test timeout check with $PROVISION_HOW"
        rlRun "$tmt_command /internal/timeout" 2
        assert_check_result "Test results have failed timeout check" "/internal/timeout" "internal/timeout" "fail"
    rlPhaseEnd

    rlPhaseStartTest "Test abort & interrupt check with $PROVISION_HOW"
        rlRun "$tmt_command /internal/abort" 2
        assert_check_result "Test results have failed abort check" "/internal/abort" "internal/abort" "fail"
        assert_check_result "Test results have failed interrupt check" "/internal/abort" "internal/interrupt" "fail"
    rlPhaseEnd

    rlPhaseStartTest "Test permission check with $PROVISION_HOW"
        rlRun "$tmt_command /internal/permission" 2
        assert_check_result "Test results have failed permission check" "/internal/permission" "internal/permission" "fail"
    rlPhaseEnd

    rlPhaseStartTest "Test invocation check with $PROVISION_HOW"
        rlRun "$tmt_command /internal/invocation" 2
        assert_check_result "Test results have failed invocation check" "/internal/invocation" "internal/invocation" "fail"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
