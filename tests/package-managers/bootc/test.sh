#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    for user in root cloud-user; do
        # Testing virtual provisioner with bootc image
        rlPhaseStartTest "Virtual provisioner with CentOS Stream 10 bootc image ($user)"
            rlRun "run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"
            rlRun -s "tmt -vvv run --scratch -i $run plan --name /plans/centos-stream-10/$user"
            rlAssertGrep "Booted image: containers-storage:localhost/tmt/bootc/\\w+-\\w+-\\w+-\\w+-\\w+" $rlRun_LOG -P
            rlAssertGrep "Trying to pull quay.io/testing-farm/centos-bootc:stream10" $rlRun_LOG
            rlRun "rm -rf $run" 0 "Remove run directory"
        rlPhaseEnd

        # Testing virtual provisioner with bootc image, skipping prepare step
        # Should not install anything and rebuild the image
        rlPhaseStartTest "Virtual provisioner with CentOS Stream 10 bootc image, skip prepare ($user)"
            rlRun "run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"
            rlRun -s "tmt -vvv run --scratch -i $run --skip prepare plan --name /plans/centos-stream-10/$user"
            rlAssertGrep "Booted image: quay.io/testing-farm/centos-bootc:stream10" $rlRun_LOG
            rlAssertNotGrep "Trying to pull quay.io/testing-farm/centos-bootc:stream10" $rlRun_LOG
            rlRun "rm -rf $run" 0 "Remove run directory"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
