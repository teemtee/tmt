#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Single device access test"
        # Test the plan with single device access enabled
        rlRun "export TMT_EXPOSABLE_RUNNER_DEVICES='/dev/random'" 0 "Set device allowlist"
        rlRun -s "tmt run -vvvddd --scratch --id $run  plan --name /plan/with-random test --name /test-random-device"
        # Check if device access was configured (look for --device /dev/random in logs)
        rlAssertGrep "--device /dev/random" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Multiple devices access test"
        # Test the plan with multiple devices access enabled
        rlRun "export TMT_EXPOSABLE_RUNNER_DEVICES='/dev/random /dev/urandom'" 0 "Set device allowlist"
        rlRun -s "tmt run -vvvddd --scratch --id $run  plan --name /plan/with-multiple-devices test --name /test-multiple-devices"
        # Check if multiple device access was configured
        rlAssertGrep "--device /dev/random" $rlRun_LOG
        rlAssertGrep "--device /dev/urandom" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Device access failure test when allowlist not configured"
        # Test that device access fails when TMT_EXPOSABLE_RUNNER_DEVICES is not set
        # Temporarily unset the environment variable to test security restriction
        rlRun "unset TMT_EXPOSABLE_RUNNER_DEVICES"
        rlRun -s "tmt run -vvvddd --scratch --id $run  plan --name /plan/with-random test --name /test-random-device" 2 "Device access should fail without allowlist"
        # Check that the failure is due to security allowlist validation
        rlAssertGrep "Device '/dev/random' cannot be exposed. The device is not in the security allowlist" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
