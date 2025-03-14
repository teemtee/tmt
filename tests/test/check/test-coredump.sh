#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    rlAssertEquals "$1" "coredump:$2" "$(yq -r ".[] | select(.name == \"$4\") | .check | .[] | select(.event == \"$3\") | \"\\(.name):\\(.result)\"" $results)"
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "results=$run/plan/execute/results.yaml"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Test harmless run with $PROVISION_HOW"
        rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /coredump/harmless"
        rlRun "cat $results"

        if [ "$PROVISION_HOW" = "container" ]; then
            # Container won't have required capabilities
            assert_check_result "coredump as a before-test should skip with containers" "skip" "before-test" "/coredump/harmless"
            assert_check_result "coredump as an after-test should skip with containers" "skip" "after-test" "/coredump/harmless"
        else
            # Other provisioners should pass with no crashes
            assert_check_result "coredump as a before-test should pass" "pass" "before-test" "/coredump/harmless"
            assert_check_result "coredump as an after-test should pass" "pass" "after-test" "/coredump/harmless"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Test segfault with $PROVISION_HOW"
        if [ "$PROVISION_HOW" = "container" ]; then
            # Container won't have required capabilities, expect success
            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /coredump/segfault"
        else
            # Other provisioners should detect the crash, expect failure
            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /coredump/segfault" "1"
        fi
        rlRun "cat $results"

        if [ "$PROVISION_HOW" = "container" ]; then
            # Container won't have required capabilities
            assert_check_result "coredump as a before-test should skip with containers" "skip" "before-test" "/coredump/segfault"
            assert_check_result "coredump as an after-test should skip with containers" "skip" "after-test" "/coredump/segfault"
        else
            # Other provisioners should detect the crash
            assert_check_result "coredump as a before-test should pass" "pass" "before-test" "/coredump/segfault"
            assert_check_result "coredump as an after-test should fail" "fail" "after-test" "/coredump/segfault"

            # Verify coredump was captured
            rlRun "ls -l $run/plan/execute/data/guest/default-0/coredump/segfault-1/checks/dump._usr_bin_bash_SIGSEGV_*.core"
            rlLogInfo "$(ls -l $run/plan/execute/data/guest/default-0/coredump/segfault-1/checks/)"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
