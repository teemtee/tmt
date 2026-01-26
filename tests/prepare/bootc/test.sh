#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    # Test prepare/shell on bootc guest - should use Containerfile collection
    rlPhaseStartTest "Prepare/shell on bootc guest - install tree package"
        rlRun "run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"
        rlRun -s "tmt -dddvvv run --scratch -i $run plan --name /plans/centos-stream-10/prepare-shell"

        # Verify the prepare/shell command was collected
        rlAssertGrep "Collected command for Containerfile" $rlRun_LOG

        # Verify the container image was built
        rlAssertGrep "building container image from collected commands" $rlRun_LOG

        # Verify bootc switch was called
        rlAssertGrep "switching to new image" $rlRun_LOG

        # Verify reboot happened
        rlAssertGrep "rebooting to apply new image" $rlRun_LOG

        # Verify tree --version ran successfully in the test
        rlAssertGrep "tree v" $rlRun_LOG

        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
