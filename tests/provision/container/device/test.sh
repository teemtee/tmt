#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Single device access test"
        # Test the plan with single device access enabled
        rlRun -s "tmt run -vvvddd --id $run  plan --name /plan-with-random test --name /test-random-device"
        # Check if device access was configured (look for --device /dev/random in logs)
        rlAssertGrep "--device /dev/random" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Multiple devices access test"
        # Test the plan with multiple devices access enabled
	rlRun -s "tmt run -vvvddd --id $run  plan --name /plan-with-multiple-devices test --name /test-multiple-devices"
        # Check if multiple device access was configured
	rlAssertGrep "--device /dev/random" $rlRun_LOG
	rlAssertGrep "--device /dev/urandom" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
