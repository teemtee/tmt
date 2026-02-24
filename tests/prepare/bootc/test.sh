#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"
    rlPhaseEnd

    # Test prepare/shell on bootc guest - should use Containerfile collection
    rlPhaseStartTest "Prepare/shell on bootc guest - install tree package"
        rlRun -s "tmt -dddvvv run --scratch -i $run plan --name /plans/centos-stream-10/prepare-shell"

        # Verify the prepare/shell command was collected                                     ..
        rlAssertGrep "Collected command for Containerfile" $rlRun_LOG

        # Verify the container image was built
        rlAssertGrep "building container image from collected commands" $rlRun_LOG

        # Verify bootc switch was called
        rlAssertGrep "switching to new image" $rlRun_LOG

        # Verify reboot happened
        rlAssertGrep "rebooting to apply new image" $rlRun_LOG

        # Verify tree --version ran successfully in the test
        rlAssertGrep "tree v" $rlRun_LOG
    rlPhaseEnd

    # Test prepare/install on bootc guest - should install rpm via Containerfile
    rlPhaseStartTest "Prepare/install on bootc guest - install tree package from rpm"
        # Download tree RPM
        rlRun "curl -LO https://mirror.stream.centos.org/10-stream/BaseOS/x86_64/os/Packages/tree-2.1.0-8.el10.x86_64.rpm"

        # Run tmt
        rlRun -s "tmt -dddvvv run --scratch -i $run plan --name /plans/centos-stream-10/prepare-install"

        # Verify the container image was built
        rlAssertGrep "Trying to pull quay.io/testing-farm/centos-bootc:stream10" $rlRun_LOG
        rlAssertGrep "package: building container image with dependencies" $rlRun_LOG

        # Verify bootc switch was called
        rlAssertGrep "switching to new image" $rlRun_LOG

        # Verify reboot happened
        rlAssertGrep "rebooting to apply new image" $rlRun_LOG

        # Verify tree --version ran successfully in the test
        rlAssertGrep "tree v" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
