#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    rlAssertEquals "$1" "dmesg:$2" "$(yq -r ".[] | .check | .[] | select(.event == \"$3\") | \"\\(.name):\\(.result)\"" $results)"
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        rlRun "results=$run/plan/execute/results.yaml"
        rlRun "dump_before=$run/plan/execute/data/guest/default-0/dmesg-1/checks/dmesg-before-test.txt"
        rlRun "dump_after=$run/plan/execute/data/guest/default-0/dmesg-1/checks/dmesg-after-test.txt"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    for method in ${PROVISION_METHODS:-local}; do
        rlPhaseStartTest "Test dmesg check with $method"
            rlRun "tmt run --id $run --scratch -a -vv provision -h $method test -n dmesg"

            rlRun "cat $results"

            rlAssertExists "$dump_before"
            if [ "$method" = "container" ]; then
                assert_check_result "dmesg as a before-test should fail with containers" "error" "before-test"

                if rlIsFedora ">=40"; then
                    rlAssertGrep "dmesg: read kernel buffer failed: Operation not permitted" "$dump_before"
                else
                    rlAssertGrep "dmesg: read kernel buffer failed: Permission denied" "$dump_before"
                fi
            else
                assert_check_result "dmesg as a before-test should pass" "pass" "before-test"
            fi
            rlLogInfo "$(cat $dump_before)"

            rlAssertExists "$dump_after"
            if [ "$method" = "container" ]; then
                assert_check_result "dmesg as a before-test should fail with containers" "error" "after-test"

                if rlIsFedora ">=40"; then
                    rlAssertGrep "dmesg: read kernel buffer failed: Operation not permitted" "$dump_after"
                else
                    rlAssertGrep "dmesg: read kernel buffer failed: Permission denied" "$dump_after"
                fi
            else
                assert_check_result "dmesg as a before-test should pass" "pass" "after-test"
            fi
            rlLogInfo "$(cat $dump_after)"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
