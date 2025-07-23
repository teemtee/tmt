#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    comment="$1"
    result="$2"
    event="$3"
    name="/journal/$4"
    rlAssertEquals "$comment" "journal:$result" "$(yq -r ".[] | select(.name == \"$name\") | .check | .[] | select(.event == \"$event\") | \"\\(.name):\\(.result)\"" $results)"
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        rlRun "results=$run/plan/execute/results.yaml"
        rlRun "harmless=$run/plan/execute/data/guest/default-0/journal/harmless-1"
        rlRun "segfault=$run/plan/execute/data/guest/default-0/journal/segfault-1"
        rlRun "custom_patterns=$run/plan/execute/data/guest/default-0/journal/custom-patterns-1"
        rlRun "multiple_reports=$run/plan/execute/data/guest/default-0/journal/multiple-reports-1"
        rlRun "unit_test=$run/plan/execute/data/guest/default-0/journal/unit-test-1"
        rlRun "ignore_test=$run/plan/execute/data/guest/default-0/journal/ignore-test-1"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Test journal check with $PROVISION_HOW in harmless run"
        rlRun "journal_log=$harmless/checks/journal.txt"

        rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal/harmless"
        rlRun "cat $results"

        if [ "$PROVISION_HOW" = "container" ]; then
            assert_check_result "journal as an after-test should skip with containers" "skip" "after-test" "harmless"

            rlAssertNotExists "$journal_log"

        else
            assert_check_result "journal as an after-test should pass" "pass" "after-test" "harmless"

            rlAssertExists "$journal_log"
            rlLogInfo "$(cat $journal_log)"

        fi
    rlPhaseEnd

    if [ "$PROVISION_HOW" = "virtual" ]; then
        # Segfault test only reproducible with virtual (needs root)
        rlPhaseStartTest "Test journal check with $PROVISION_HOW with a segfault"
            rlRun "journal_log=$segfault/checks/journal.txt"

            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal/segfault" "1"
            rlRun "cat $results"

            assert_check_result "journal as an after-test should fail" "fail" "after-test" "segfault"

            rlAssertExists "$journal_log"
            rlLogInfo "$(cat $journal_log)"
        rlPhaseEnd

        # Reproducible only with reliable dmesg content, e.g. after booting a fresh VM
        rlPhaseStartTest "Test journal check with $PROVISION_HOW with custom patterns"
            rlRun "journal_log=$custom_patterns/checks/journal.txt"

            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal/custom-patterns" "1"
            rlRun "cat $results"

            assert_check_result "journal as an after-test should fail" "fail" "after-test" "custom-patterns"

            rlAssertExists "$journal_log"
            rlLogInfo "$(cat $journal_log)"
        rlPhaseEnd

        rlPhaseStartTest "Test multiple journal reports with $PROVISION_HOW"
            rlRun "journal_log=$multiple_reports/checks/journal.txt"

            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal/multiple-reports"
            rlRun "cat $results"

            rlLogInfo "$(cat $journal_log)"
            rlAssertEquals "There should be 3 reports after the test" \
                           "$(grep 'journal log' $journal_log | wc -l)" "3"
        rlPhaseEnd

        rlPhaseStartTest "Test journal check with unit"
            rlRun "journal_log=$unit_test/checks/journal.txt"
            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal/unit-test" "1"
            rlRun "cat $results"
            assert_check_result "journal as an after-test should fail" "fail" "after-test" "unit-test"
            rlAssertExists "$journal_log"
            rlLogInfo "$(cat $journal_log)"
        rlPhaseEnd

        rlPhaseStartTest "Test journal check with ignore-pattern"
            rlRun "journal_log=$ignore_test/checks/journal.txt"
            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /journal/ignore-test"
            rlRun "cat $results"
            assert_check_result "journal as an after-test should pass" "pass" "after-test" "ignore-test"
            rlAssertExists "$journal_log"
            rlLogInfo "$(cat $journal_log)"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
