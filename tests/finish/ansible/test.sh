#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
    rlPhaseEnd

    rlPhaseStartTest "Test ($PROVISION_HOW)"
        # Prepare common options, run given method
        tmt="tmt run -i $run --scratch"
        rlRun "$tmt -av provision -h $PROVISION_HOW"

        # Check that created file is synced back
        rlRun "ls -l $run/plan/data"
        rlAssertExists "$run/plan/data/my_file.txt"

        # For container provision try centos images as well
        if [[ $PROVISION_HOW == container ]]; then
            rlRun "$tmt -av finish provision -h $PROVISION_HOW -i centos:7"
            rlRun "$tmt -av finish provision -h $PROVISION_HOW -i centos:stream8"
        fi

        # After the local provision remove the test file
        if [[ $PROVISION_HOW == local ]]; then
            rlRun "sudo rm -f /tmp/finished"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r $run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
