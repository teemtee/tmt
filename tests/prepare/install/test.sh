#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"

        rlRun "export TMT_BOOT_TIMEOUT=300"
        rlRun "export TMT_CONNECT_TIMEOUT=300"
    rlPhaseEnd

    # Prepare the common tmt command
    tmt="tmt run --all --id $run --scratch -vvv"

    # Run basic tests against the given provision method
    provision="provision --how $PROVISION_HOW"

    rlPhaseStartTest "Install an existing package ($PROVISION_HOW)"
        rlRun "$tmt $provision plan --name existing"
    rlPhaseEnd

    rlPhaseStartTest "Report a missing package ($PROVISION_HOW)"
        rlRun "$tmt $provision plan --name missing" 2
    rlPhaseEnd

    # Add one extra CoreOS run for virtual provision
    if [[ "$PROVISION_HOW" == "virtual" ]]; then
        provision="provision --how $PROVISION_HOW --image fedora-coreos"

        rlPhaseStartTest "Install an existing package ($PROVISION_HOW, CoreOS)"
            rlRun "$tmt $provision plan --name existing"
            rlAssertGrep "rpm-ostree install.*tree" $run/log.txt
            rlAssertNotGrep "rpm-ostree install.*/usr/bin/flock" $run/log.txt
        rlPhaseEnd

        rlPhaseStartTest "Report a missing package ($PROVISION_HOW, CoreOS)"
            rlRun "$tmt $provision plan --name missing" 2
        rlPhaseEnd
    fi

    # And a couple of additional tests with container provision
    if [[ "$PROVISION_HOW" == "container" ]]; then
        rlPhaseStartTest "Provide package on the command line"
            rlRun "tmt run -vvvr plan --default \
                provision --how container \
                prepare --how install --package tree \
                finish"
        rlPhaseEnd

        rlPhaseStartTest "Just enable copr"
            rlRun "$tmt plan --name copr"
        rlPhaseEnd

        rlPhaseStartTest "Escape package names"
            rlRun "$tmt plan --name escape"
        rlPhaseEnd

        rlPhaseStartTest "Exclude selected packages"
            rlRun "$tmt plan --name exclude"
        rlPhaseEnd

        rlPhaseStartTest "Install from epel7 copr"
            rlRun "$tmt plan --name epel7"
        rlPhaseEnd

        rlPhaseStartTest "Install remote packages"
            rlRun "$tmt plan --name epel8-remote"
        rlPhaseEnd

        rlPhaseStartTest "Install debuginfo packages"
            rlRun "$tmt plan --name debuginfo"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
