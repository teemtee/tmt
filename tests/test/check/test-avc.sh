#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    rlAssertEquals "$1" "avc:$2" "$(yq -r ".[] | .check | .[] | select(.event == \"$3\") | \"\\(.name):\\(.result)\"" $results)"
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        rlRun "results=$run/plan/execute/results.yaml"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    for method in ${PROVISION_METHODS:-local}; do
        rlPhaseStartTest "Test harmless AVC check with $method"
            rlRun "avc_log=$run/plan/execute/data/guest/default-0/avc/harmless-1/tmt-avc-after-test.txt"

            rlRun "tmt -c provision_method=$method run --id $run --scratch -a -vv provision -h $method test -n /avc/harmless"

            rlRun "cat $results"
            rlRun "cat $avc_log"

            rlAssertExists "$avc_log"

            assert_check_result "avc as an after-test should pass" "pass" "after-test"

            rlAssertGrep "<no matches>" "$avc_log"
        rlPhaseEnd

        rlPhaseStartTest "Test nasty AVC check with $method"
            rlRun "tmt -c provision_method=$method run --id $run --scratch -a -vv provision -h $method test -n /avc/nasty"

            rlRun "avc_log=$run/plan/execute/data/guest/default-0/avc/nasty-1/tmt-avc-after-test.txt"

            rlRun "cat $results"
            rlRun "cat $avc_log"

            rlAssertExists "$avc_log"

            assert_check_result "avc as an after-test should report AVC denials" "fail" "after-test"

            rlAssertGrep "avc:  denied" "$avc_log"
            rlAssertGrep "path=/root/passwd.log" "$avc_log"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
