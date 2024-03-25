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
        rlRun "segfault=$run/plan/execute/data/guest/default-0/dmesg/segfault-1"
        rlRun "custom_patterns=$run/plan/execute/data/guest/default-0/dmesg/custom-patterns-1"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Test dmesg check with $PROVISION_HOW in harmless run"
        rlRun "dump_before=$harmless/checks/dmesg-before-test.txt"
        rlRun "dump_after=$harmless/checks/dmesg-after-test.txt"

        rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /dmesg/harmless"
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

        else
            assert_check_result "dmesg as an after-test should pass" "pass" "after-test" "harmless"

            rlAssertExists "$dump_after"
            rlLogInfo "$(cat $dump_after)"

        fi
    rlPhaseEnd

    if [ "$PROVISION_HOW" = "virtual" ]; then
        # Segfault test only reproducible with virtual (needs root)
        rlPhaseStartTest "Test dmesg check with $PROVISION_HOW with a segfault"
            rlRun "dump_before=$segfault/checks/dmesg-before-test.txt"
            rlRun "dump_after=$segfault/checks/dmesg-after-test.txt"

            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /dmesg/segfault"
            rlRun "cat $results"

            assert_check_result "dmesg as a before-test should pass" "pass" "before-test" "segfault"

            rlAssertExists "$dump_before"
            rlLogInfo "$(cat $dump_before)"

            assert_check_result "dmesg as an after-test should fail" "fail" "after-test" "segfault"

            rlAssertExists "$dump_after"
            rlLogInfo "$(cat $dump_after)"
        rlPhaseEnd

        # Reproducible only with reliable dmesg content, e.g. after booting a fresh VM
        rlPhaseStartTest "Test dmesg check with $PROVISION_HOW with custom patterns"
            rlRun "dump_before=$custom_patterns/checks/dmesg-before-test.txt"
            rlRun "dump_after=$custom_patterns/checks/dmesg-after-test.txt"

            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /dmesg/custom-patterns"
            rlRun "cat $results"

            assert_check_result "dmesg as a before-test should fail" "fail" "before-test" "custom-patterns"

            rlAssertExists "$dump_before"
            rlLogInfo "$(cat $dump_before)"

            assert_check_result "dmesg as an after-test should pass" "pass" "after-test" "custom-patterns"

            rlAssertExists "$dump_after"
            rlLogInfo "$(cat $dump_after)"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
