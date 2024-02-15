#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    comment="$1"
    result="$2"
    event="$3"
    name="/dmesg/$4"
    rlAssertEquals "$comment" "dmesg:$result" "$(yq -r ".[] | select(.name == \"$name\") | .check | .[] | select(.event == \"$event\") | \"\\(.name):\\(.result)\"" $results)"
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        rlRun "results=$run/plan/execute/results.yaml"
        rlRun "harmless=$run/plan/execute/data/guest/default-0/dmesg/harmless-1"
        rlRun "segfault=$run/plan/execute/data/guest/default-0/dmesg/segfault-2"
        rlRun "dump_before=$harmless/checks/dmesg-before-test.txt"
        rlRun "dump_after=$harmless/checks/dmesg-after-test.txt"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Test dmesg check with $PROVISION_HOW"
        # Segfault test only reproducible with virtual (needs root)
        if [ "$PROVISION_HOW" = "virtual" ]; then
            test_name=/dmesg
        else
            test_name=/dmesg/harmless
        fi

        rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n $test_name"

        rlRun "cat $results"

        if [ "$PROVISION_HOW" = "container" ]; then
            assert_check_result "dmesg as a before-test should skip with containers" "skip" "before-test" "harmless"

            rlAssertNotExists "$dump_before"

        else
            assert_check_result "dmesg as a before-test should pass" "pass" "before-test" "harmless"

            rlAssertExists "$dump_before"
            rlLogInfo "$(cat $dump_before)"
        fi

        if [ "$PROVISION_HOW" = "container" ]; then
            assert_check_result "dmesg as an after-test should skip with containers" "skip" "after-test" "harmless"

            rlAssertNotExists "$dump_after"

        elif [ "$PROVISION_HOW" = "virtual" ]; then
            assert_check_result "dmesg as an after-test should fail" "fail" "after-test" "segfault"

            rlAssertExists "$dump_after"
            rlLogInfo "$(cat $dump_after)"

            rlAssertGrep "Some segfault happened" "$segfault/checks/dmesg-after-test.txt"

        else
            assert_check_result "dmesg as an after-test should pass" "pass" "after-test" "harmless"

            rlAssertExists "$dump_after"
            rlLogInfo "$(cat $dump_after)"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
