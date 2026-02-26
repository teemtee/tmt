#!/bin/bash
# Outer beakerlib test for the nvr-debug suite.
# RPMs are built inside each container by build-repos.sh (plan prepare step).
# Each plan installs its own .repo files via the artifact provider.

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "testdir=$(mktemp -d)" 0 "Create test directory"
        rlRun "cp -a data $testdir"
        rlRun "pushd $testdir/data"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"
        setup_distro_environment
    rlPhaseEnd

    while IFS= read -r plan; do
        rlPhaseStartTest "$plan"
            rlRun "tmt run -i $run --scratch -vvv --all \
                plan --name $plan \
                provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name" \
                0 "$plan"
        rlPhaseEnd
    done < <(tmt plans ls)

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run $testdir" 0 "Remove run and test directories"
    rlPhaseEnd
rlJournalEnd
