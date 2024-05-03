#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    rlAssertEquals "$1" "watchdog:$2" "$(yq -r ".[] | .check | .[] | select(.event == \"$3\") | \"\\(.name):\\(.result)\"" $results)"
}


rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"

        # Using /var/tmp instead of /tmp - we need the directory to survive
        # reboot, under /tmp it would be removed :/
        rlRun "run=\$(mktemp -d -p /var/tmp)" 0 "Create run directory"

        rlRun "results=$run/plan/execute/results.yaml"

        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Test guest watchdog ping with $PROVISION_HOW provisioning"
        rlRun "test_dir=$run/plan/execute/data/guest/default-0/watchdog/ping-1"
        rlRun "log=$run/log.txt"
        rlRun "test_log=$test_dir/output.txt"
        rlRun "watchdog_log=$test_dir/checks/tmt-watchdog.txt"

        if [ "$PROVISION_HOW" = "container" ]; then
            rlRun "tmt -c provision_method=$PROVISION_HOW run --id $run --scratch -a -vv provision -h $PROVISION_HOW                     test -n /watchdog" 1

        elif [ "$PROVISION_HOW" = "virtual" ]; then
            rlRun "tmt -c provision_method=$PROVISION_HOW run --id $run --scratch -a -vv provision -h $PROVISION_HOW --connection system test -n /watchdog"

        else
            rlDie "Provision method $PROVISION_HOW is not supported by the test."
        fi

        rlRun "cat $results"
        rlRun "cat $test_log"

        if [ "$PROVISION_HOW" = "container" ]; then
            rlRun "grep -E '\\[watchdog\\][[:space:]]+warn: Ping against this guest is not supported, disabling.' $log"
            rlRun "grep -E '\\[watchdog\\][[:space:]]+warn: SSH ping against this guest is not supported, disabling.' $log"

            assert_check_result "watchdog as an after-test should pass" "pass" "after-test"

            rlAssertGrep    "TMT_REBOOT_COUNT=\"0\""       $test_log
            rlAssertGrep    "TMT_TEST_RESTART_COUNT=\"0\"" $test_log
            rlAssertNotGrep "TMT_REBOOT_COUNT=\"1\""       $test_log
            rlAssertNotGrep "TMT_TEST_RESTART_COUNT=\"1\"" $test_log
            rlAssertGrep "/proc/sysrq-trigger: Read-only file system" $test_log

        elif [ "$PROVISION_HOW" = "virtual" ]; then
            rlRun "cat $watchdog_log"

            rlRun "grep -E '\\[watchdog\\][[:space:]]+warn: Ping against this guest is not supported, disabling.' $log"

            assert_check_result "watchdog as an after-test should pass" "pass" "after-test"

            rlAssertGrep "TMT_REBOOT_COUNT=\"0\""       $test_log
            rlAssertGrep "TMT_TEST_RESTART_COUNT=\"0\"" $test_log
            rlAssertGrep "TMT_REBOOT_COUNT=\"1\""       $test_log
            rlAssertGrep "TMT_TEST_RESTART_COUNT=\"1\"" $test_log
            rlAssertGrep "++ exit 0" $test_log

            rlAssertGrep "# ssh-ping reported"     $watchdog_log
            rlAssertGrep "# failed 1 of 3 allowed" $watchdog_log
            rlAssertGrep "# failed 2 of 3 allowed" $watchdog_log
            rlAssertGrep "# failed 3 of 3 allowed" $watchdog_log

            rlRun "grep -E '\\[watchdog\\][[:space:]]+fail: exhausted 3 SSH ping attempts' $log"
            rlAssertGrep "Hard reboot during test '/watchdog/ping' with reboot count 1 and test restart count 1." $log
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"

        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
