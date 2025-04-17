#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

function assert_check_result () {
    rlAssertEquals "$1" "coredump:$2" "$(yq -r ".[] | select(.name == \"$4\") | .check | .[] | select(.event == \"$3\") | \"\\(.name):\\(.result)\"" $results)"
}

function check_systemd_availability () {
    has_systemd=true
    if [ "$PROVISION_HOW" = "container" ] || { [ "$PROVISION_HOW" = "local" ] && ! systemctl --version &>/dev/null; }; then
        has_systemd=false
    fi
    echo $has_systemd
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

        # Check if systemd is available in the provisioner
        has_systemd=$(check_systemd_availability)

        if [ "$has_systemd" = "false" ]; then
            # Container or local without systemd won't have required capabilities
            assert_check_result "coredump as a before-test should skip without systemd" "skip" "before-test" "/coredump/harmless"
            assert_check_result "coredump as an after-test should skip without systemd" "skip" "after-test" "/coredump/harmless"
        else
            # Other provisioners should pass with no crashes
            assert_check_result "coredump as a before-test should pass" "pass" "before-test" "/coredump/harmless"
            assert_check_result "coredump as an after-test should pass" "pass" "after-test" "/coredump/harmless"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Test segfault with $PROVISION_HOW"
        # Check if systemd is available in the provisioner
        has_systemd=$(check_systemd_availability)

        if [ "$has_systemd" = "false" ]; then
            # No systemd means no coredump capabilities, expect success
            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /coredump/segfault"
        else
            # Other provisioners should detect the crash, expect failure
            rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /coredump/segfault" "1"
        fi
        rlRun "cat $results"

        if [ "$has_systemd" = "false" ]; then
            # No systemd means no coredump capabilities
            assert_check_result "coredump as a before-test should skip without systemd" "skip" "before-test" "/coredump/segfault"
            assert_check_result "coredump as an after-test should skip without systemd" "skip" "after-test" "/coredump/segfault"
        else
            # Other provisioners should detect the crash
            assert_check_result "coredump as a before-test should pass" "pass" "before-test" "/coredump/segfault"
            assert_check_result "coredump as an after-test should fail" "fail" "after-test" "/coredump/segfault"

            # Verify coredump was captured
            rlRun find $run/plan/execute/data/guest/default-0/coredump/segfault-1/checks/ -maxdepth 1 \  # grep needed as find returns 0 even without match
            \( -name 'dump._usr_bin_bash_SIGSEGV_*.core' -o -name 'dump._usr_bin_sleep_SIGSEGV_*.core' \) -print | grep -q .
            rlLogInfo "$(ls -l $run/plan/execute/data/guest/default-0/coredump/segfault-1/checks/)"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Test ignore pattern with $PROVISION_HOW"
        # This test uses the same segfault code but with a pattern to ignore it
        # Check if systemd is available in the provisioner
        has_systemd=$(check_systemd_availability)

        # This test should pass regardless of systemd availability
        rlRun "tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n /coredump/ignore-pattern"
        rlRun "cat $results"

        if [ "$has_systemd" = "false" ]; then
            # No systemd means no coredump capabilities
            assert_check_result "coredump as a before-test should skip without systemd" "skip" "before-test" "/coredump/ignore-pattern"
            assert_check_result "coredump as an after-test should skip without systemd" "skip" "after-test" "/coredump/ignore-pattern"
        else
            # Even though there's a crash, it should pass because of the ignore pattern
            assert_check_result "coredump as a before-test should pass" "pass" "before-test" "/coredump/ignore-pattern"
            assert_check_result "coredump as an after-test should pass" "pass" "after-test" "/coredump/ignore-pattern"

            # Verify the crash was still logged even though it was ignored
            rlRun "ls -l $run/plan/execute/data/guest/default-0/coredump/ignore-pattern-1/checks/"
            rlLogInfo "$(ls -l $run/plan/execute/data/guest/default-0/coredump/ignore-pattern-1/checks/)"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
