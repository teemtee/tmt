#!/bin/bash
# Outer beakerlib test for the nvr-debug suite.
# RPMs are built once on the controller by build-repos.sh, then synced into
# each container. Each plan installs its own .repo files via the artifact provider.

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup "Prepare test environment"
        PROVISION_HOW=${PROVISION_HOW:-container}
        rlRun "testdir=$(mktemp -d)" 0 "Create test directory"
        rlRun "cp -a data $testdir" 0 "Copy test data"
        rlRun "pushd $testdir/data" 0 "Enter test directory"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"
        setup_distro_environment
    rlPhaseEnd

    rlPhaseStartSetup "Build RPM repos"
        rlRun "./build-repos.sh" 0 "Build RPM repos"
    rlPhaseEnd

    for plan in $(tmt plans ls); do
        rlPhaseStartTest "$plan"
            rlRun "tmt run -i $run --scratch -vvv --all \
                plan --name $plan \
                provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name" \
                0 "$plan"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run $testdir" 0 "Remove run and test directories"
    rlPhaseEnd
rlJournalEnd
