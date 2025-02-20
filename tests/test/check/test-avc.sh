#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    rlAssertEquals "$1" "avc:$2" "$(yq -r ".[] | select(.name == \"$4\")  | .check | .[] | select(.event == \"$3\") | \"\\(.name):\\(.result)\"" $results)"
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        rlRun "results=$run/plan/execute/results.yaml"

        rlRun "pushd data"
    rlPhaseEnd

    for method in checkpoint timestamp; do
        rlPhaseStartTest "Run /avc tests with $PROVISION_HOW"
            rlRun "tmt -c provision_method=$PROVISION_HOW run --id $run --scratch -a -vvv provision -h $PROVISION_HOW test -n /avc/$method" "1"
            rlRun "cat $results"
        rlPhaseEnd

        rlPhaseStartTest "Test harmless AVC check with $PROVISION_HOW"
            rlRun "avc_log=$run/plan/execute/data/guest/default-0/avc/$method/harmless-2/checks/avc.txt"
            rlAssertExists "$avc_log"
            rlRun "cat $avc_log"

            assert_check_result "avc as an after-test should pass" "pass" "after-test" "/avc/$method/harmless"

            rlAssertGrep "<no matches>" "$avc_log"
            rlAssertGrep "## mark" "$avc_log"

            if [ "$method" = "checkpoint" ]; then
                /bin/true
            else
                rlAssertGrep "export 'AVC_SINCE=[[:digit:]]{2}/[[:digit:]]{2}/[[:digit:]]{2} [[:digit:]]{2}:[[:digit:]]{2}:[[:digit:]]{2}'" "$avc_log" -E
            fi
        rlPhaseEnd

        rlPhaseStartTest "Test nasty AVC check with $PROVISION_HOW"
            rlRun "avc_log=$run/plan/execute/data/guest/default-0/avc/$method/nasty-1/checks/avc.txt"
            rlAssertExists "$avc_log"
            rlRun "cat $avc_log"

            assert_check_result "avc as an after-test should report AVC denials" "fail" "after-test" "/avc/$method/nasty"

            rlAssertGrep "avc:  denied" "$avc_log"
            rlAssertGrep "path=/root/passwd.log" "$avc_log"
            rlAssertGrep "## mark" "$avc_log"

            if [ "$method" = "checkpoint" ]; then
                /bin/true
            else
                rlAssertGrep "export 'AVC_SINCE=[[:digit:]]{2}/[[:digit:]]{2}/[[:digit:]]{2} [[:digit:]]{2}:[[:digit:]]{2}:[[:digit:]]{2}'" "$avc_log" -E
            fi
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
