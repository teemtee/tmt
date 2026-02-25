#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"
    rlPhaseEnd

    # # Test prepare/shell on bootc guest - should use Containerfile collection
    # rlPhaseStartTest "Prepare/shell on bootc guest - install tree package"
    #     rlRun -s "tmt -dddvvv run --scratch -i $run plan --name /plans/centos-stream-10/prepare-shell"
    #
    #     # Verify the prepare/shell command was collected                                     ..
    #     rlAssertGrep "Collected command for Containerfile" $rlRun_LOG
    #
    #     # Verify the container image was built
    #     rlAssertGrep "building container image from collected commands" $rlRun_LOG
    #
    #     # Verify bootc switch was called
    #     rlAssertGrep "switching to new image" $rlRun_LOG
    #
    #     # Verify reboot happened
    #     rlAssertGrep "rebooting to apply new image" $rlRun_LOG
    #
    #     # Verify tree --version ran successfully in the test
    #     rlAssertGrep "tree v" $rlRun_LOG
    # rlPhaseEnd

    # Test prepare/install on bootc guest - should install rpm via Containerfile
    rlPhaseStartTest "Prepare/install on bootc guest - install tree package from rpm"
        # Download tree RPM
        rlRun -s "koji -p stream list-tagged --arch x86_64 --rpms --latest --quiet c10s-candidate tree-pkg | head -1"
        rlRun "curl -LO https://mirror.stream.centos.org/10-stream/BaseOS/x86_64/os/Packages/$(cat $rlRun_LOG).rpm"

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
        rlRun "rm -f tree-*.rpm" 0 "Remove tree rpm"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
