#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    comment="$1"
    result="$2"
    event="$3"
    name="/journal-dmesg/$4"
    rlAssertEquals "$comment" "journal-dmesg:$result" "$(yq -r ".[] | select(.name == \"$name\") | .check | .[] | select(.event == \"$event\") | \"\\(.name):\\(.result)\"" $results)"
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        rlRun "results=$run/plan/execute/results.yaml"
        rlRun "harmless=$run/plan/execute/data/guest/default-0/journal-dmesg/harmless-1"
        rlRun "segfault=$run/plan/execute/data/guest/default-0/journal-dmesg/segfault-1"
        rlRun "custom_patterns=$run/plan/execute/data/guest/default-0/journal-dmesg/custom-patterns-1"
        rlRun "multiple_reports=$run/plan/execute/data/guest/default-0/journal-dmesg/multiple-reports-1"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Test journal-dmesg check with $PROVISION_HOW in harmless run"
        rlRun "journal_dmesg_log=$harmless/checks/journal-dmesg.txt"

        rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal-dmesg/harmless"
        rlRun "cat $results"

        if [ "$PROVISION_HOW" = "container" ]; then
            assert_check_result "journal-dmesg as an after-test should skip with containers" "skip" "after-test" "harmless"

            rlAssertNotExists "$journal_dmesg_log"

        else
            assert_check_result "journal-dmesg as an after-test should pass" "pass" "after-test" "harmless"

            rlAssertExists "$journal_dmesg_log"
            rlLogInfo "$(cat $journal_dmesg_log)"

        fi
    rlPhaseEnd

    if [ "$PROVISION_HOW" = "virtual" ]; then
        # Segfault test only reproducible with virtual (needs root)
        rlPhaseStartTest "Test journal-dmesg check with $PROVISION_HOW with a segfault"
            rlRun "journal_dmesg_log=$segfault/checks/journal-dmesg.txt"

            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal-dmesg/segfault" "1"
            rlRun "cat $results"

            assert_check_result "journal-dmesg as an after-test should fail" "fail" "after-test" "segfault"

            rlAssertExists "$journal_dmesg_log"
            rlLogInfo "$(cat $journal_dmesg_log)"
        rlPhaseEnd

        # Reproducible only with reliable dmesg content, e.g. after booting a fresh VM
        rlPhaseStartTest "Test journal-dmesg check with $PROVISION_HOW with custom patterns"
            rlRun "journal_dmesg_log=$custom_patterns/checks/journal-dmesg.txt"

            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal-dmesg/custom-patterns" "1"
            rlRun "cat $results"

            assert_check_result "journal-dmesg as an after-test should fail" "fail" "after-test" "custom-patterns"

            rlAssertExists "$journal_dmesg_log"
            rlLogInfo "$(cat $journal_dmesg_log)"
        rlPhaseEnd

        rlPhaseStartTest "Test multiple journal-dmesg reports with $PROVISION_HOW"
            rlRun "journal_dmesg_log=$multiple_reports/checks/journal-dmesg.txt"

            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal-dmesg/multiple-reports"
            rlRun "cat $results"

            rlLogInfo "$(cat $journal_dmesg_log)"
            rlAssertEquals "There should be 3 reports after the test" \
                           "$(grep 'journalctl dmesg' $journal_dmesg_log | wc -l)" "3"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
