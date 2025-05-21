#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

function check_beakerlib_failure() {
    local log
    log=$(yq -er '.[0]' "$1") || return 1
    echo "$log" | grep -qE "^:: *Failing beakerlib test$" || return 1
    echo "$log" | grep -qE "^:: \[ [0-9]{2}:[0-9]{2}:[0-9]{2} \] :: \[ *FAIL *\] :: Command 'false' \(Expected 0, got 1\)$" || return 1
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd failure-logs"
        rlRun "set -o pipefail"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
    rlPhaseEnd

    tmt_command="tmt run --scratch -a --id ${run} execute -vv test --name"

    rlPhaseStartTest "Passing shell test has no failures"
        failure_log="${run}/plan/execute/data/guest/default-0/tests/shell/pass-1/failures.yaml"
        rlRun -s "${tmt_command} /tests/shell/pass" 0
        rlAssertGrep "pass /tests/shell/pass" $rlRun_LOG
        rlAssertExists "${failure_log}"
        rlRun "yq -e '.[0] == null and length == 0' ${failure_log}" 0 "Log does not contain failures"
    rlPhaseEnd

    rlPhaseStartTest "Failing shell test has failures"
        failure_log="${run}/plan/execute/data/guest/default-0/tests/shell/fail-1/failures.yaml"
        rlRun -s "${tmt_command} /tests/shell/fail" 1
        rlAssertGrep "fail /tests/shell/fail" $rlRun_LOG
        rlAssertExists "${failure_log}"
        rlAssertEquals "Log contains the failure line" \
            "$(yq -er '.[0]' "${failure_log}")" "Output containing fail or error."
        rlAssertNotEquals "Log does not contain irrelevant lines" \
            "$(yq -er '.[1]' "${failure_log}")" "Another output."
    rlPhaseEnd

    rlPhaseStartTest "Passing beakerlib test has no failures"
        failure_log="${run}/plan/execute/data/guest/default-0/tests/beakerlib/pass-1/failures.yaml"
        rlRun -s "${tmt_command} /tests/beakerlib/pass" 0
        rlAssertGrep "pass /tests/beakerlib/pass" $rlRun_LOG
        rlAssertExists "${failure_log}"
        rlRun "yq -e '.[0] == null and length == 0' ${failure_log}" 0 "Log does not contain failures"
    rlPhaseEnd

    rlPhaseStartTest "Failing beakerlib test has failures"
        failure_log="${run}/plan/execute/data/guest/default-0/tests/beakerlib/fail-1/failures.yaml"
        rlRun -s "${tmt_command} /tests/beakerlib/fail" 1
        rlAssertGrep "fail /tests/beakerlib/fail" $rlRun_LOG
        rlAssertExists "${failure_log}"
        rlRun "check_beakerlib_failure \"$failure_log\"" 0 "Log contains beakerlib failure"
    rlPhaseEnd
rlJournalEnd
