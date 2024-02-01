#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    rlAssertEquals "$1" "avc:$2" "$(yq -r ".[] | select(.name == \"$4\")  | .check | .[] | select(.event == \"$3\") | \"\\(.name):\\(.result)\"" $results)"
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        rlRun "results=$run/plan/execute/results.yaml"

        rlRun "pushd data"
    rlPhaseEnd

    for method in ${PROVISION_METHODS:-local}; do
        rlPhaseStartTest "Run /avc tests with $method"
            rlRun "tmt -c provision_method=$method run --id $run --scratch -a -vv provision -h $method test -n /avc"
            rlRun "cat $results"
        rlPhaseEnd

        rlPhaseStartTest "Test harmless AVC check with $method"
            rlRun "avc_log=$run/plan/execute/data/guest/default-0/avc/harmless-2/checks/avc.txt"
            rlAssertExists "$avc_log"
            rlRun "cat $avc_log"

            assert_check_result "avc as an after-test should pass" "pass" "after-test" "/avc/harmless"

            rlAssertGrep "# timestamp" "$avc_log"
            rlAssertGrep "export AVC_SINCE=\"[[:digit:]]{2}/[[:digit:]]{2}/[[:digit:]]{4} [[:digit:]]{2}:[[:digit:]]{2}:[[:digit:]]{2}\"" "$avc_log" -E
            rlAssertGrep "<no matches>" "$avc_log"
        rlPhaseEnd

        rlPhaseStartTest "Test nasty AVC check with $method"
            rlRun "avc_log=$run/plan/execute/data/guest/default-0/avc/nasty-1/checks/avc.txt"
            rlAssertExists "$avc_log"
            rlRun "cat $avc_log"

            assert_check_result "avc as an after-test should report AVC denials" "fail" "after-test" "/avc/nasty"

            rlAssertGrep "# timestamp" "$avc_log"
            rlAssertGrep "export AVC_SINCE=\"[[:digit:]]{2}/[[:digit:]]{2}/[[:digit:]]{4} [[:digit:]]{2}:[[:digit:]]{2}:[[:digit:]]{2}\"" "$avc_log" -E
            rlAssertGrep "avc:  denied" "$avc_log"
            rlAssertGrep "path=/root/passwd.log" "$avc_log"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
