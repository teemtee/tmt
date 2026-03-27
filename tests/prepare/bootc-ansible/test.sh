#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"
    rlPhaseEnd

    # Test prepare/ansible on bootc guest - should use podman connection plugin
    rlPhaseStartTest "Prepare/ansible on bootc guest - install tree package"
        rlRun -s "tmt -dddvvv run --scratch -i $run plan --name /plans/centos-stream-10/prepare-ansible"

        # Verify ansible-playbook was invoked with podman connection
        rlAssertGrep "ansible-playbook" $rlRun_LOG
        rlAssertGrep "\-c containers.podman.podman" $rlRun_LOG

        # Verify the container was committed
        rlAssertGrep "podman commit" $rlRun_LOG

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
