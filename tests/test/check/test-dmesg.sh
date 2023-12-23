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
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        rlRun "results=$run/plan/execute/results.yaml"
        rlRun "harmless=$run/plan/execute/data/guest/default-0/dmesg/harmless-1"
        rlRun "segfault=$run/plan/execute/data/guest/default-0/dmesg/segfault-2"
        rlRun "dump_before=$harmless/checks/dmesg-before-test.txt"
        rlRun "dump_after=$harmless/checks/dmesg-after-test.txt"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    for method in ${PROVISION_METHODS:-local}; do
        rlPhaseStartTest "Test dmesg check with $method"
            # Segfault test only reproducible with virtual (needs root)
            if [ "$method" = "virtual" ]; then
                test_name=/dmesg
            else
                test_name=/dmesg/harmless
            fi

            rlRun "tmt run --id $run --scratch -a -vv provision -h $method test -n $test_name"

            rlRun "cat $results"

            rlAssertExists "$dump_before"
            if [ "$method" = "container" ]; then
                assert_check_result "dmesg as a before-test should fail with containers" "error" "before-test" "harmless"

                if rlIsFedora ">=40"; then
                    rlAssertGrep "dmesg: read kernel buffer failed: Operation not permitted" "$dump_before"
                else
                    rlAssertGrep "dmesg: read kernel buffer failed: Permission denied" "$dump_before"
                fi
            else
                assert_check_result "dmesg as a before-test should pass" "pass" "before-test" "harmless"
            fi
            rlLogInfo "$(cat $dump_before)"

            rlAssertExists "$dump_after"
            if [ "$method" = "container" ]; then
                assert_check_result "dmesg as an after-test should fail with containers" "error" "after-test" "harmless"

                if rlIsFedora ">=40"; then
                    rlAssertGrep "dmesg: read kernel buffer failed: Operation not permitted" "$dump_after"
                else
                    rlAssertGrep "dmesg: read kernel buffer failed: Permission denied" "$dump_after"
                fi
            elif [ "$method" = "virtual" ]; then
                assert_check_result "dmesg as an after-test should fail" "fail" "after-test" "segfault"
                rlAssertGrep "Some segfault happened" "$segfault/checks/dmesg-after-test.txt"
            else
                assert_check_result "dmesg as an after-test should pass" "pass" "after-test" "harmless"
            fi
            rlLogInfo "$(cat $dump_after)"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
