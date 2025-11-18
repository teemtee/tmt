#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "run_kvm=\$(mktemp -d)" 0 "Create a run directory for KVM test"
        rlRun "run_multi=\$(mktemp -d)" 0 "Create a run directory for multiple devices test"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Basic container test"
        rlRun -s "tmt run --id $run -vvv plan --name /plan"
        rlAssertGrep "NAME.*Fedora Linux" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Single device access test"
        # Test the plan with single device access enabled
        rlRun -s "tmt run --id $run_kvm -dddvvv plan --name /plan-with-kvm test --name /test-kvm-device"
        # Check if device access was configured (look for --device=/dev/kvm in logs)
        rlAssertGrep ".*--device=/dev/kvm.*" $rlRun_LOG
        # The test might fail if /dev/kvm is not available on the host, but the important
        # part is that the --device=/dev/kvm flag was added to the podman command
        if rlGetPhaseState; then
            rlLogInfo "Single device was successfully passed to container"
        else
            rlLogInfo "Single device test failed (likely /dev/kvm not available on host), but configuration was applied"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Multiple devices access test"
        # Test the plan with multiple devices access enabled
        rlRun -s "tmt run --id $run_multi -dddvvv plan --name /plan-with-multiple-devices test --name /test-multiple-devices"
        # Check if multiple device access was configured
        rlAssertGrep ".*--device=/dev/kvm.*" $rlRun_LOG
        rlAssertGrep ".*--device=/dev/ttyS3.*" $rlRun_LOG
        if rlGetPhaseState; then
            rlLogInfo "Multiple devices were successfully passed to container"
        else
            rlLogInfo "Multiple devices test failed (likely devices not available on host), but configuration was applied"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlGetTestState || rlFileSubmit "$run_kvm/log.txt"
        rlGetTestState || rlFileSubmit "$run_multi/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
        rlRun "rm -r $run_kvm" 0 "Remove the KVM run directory"
        rlRun "rm -r $run_multi" 0 "Remove the multiple devices run directory"
    rlPhaseEnd
rlJournalEnd
