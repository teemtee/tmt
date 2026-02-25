#!/bin/bash
# Outer beakerlib test for the nvr-debug suite.
#
# SRPMs are pre-built and committed in data/srpms/ (see build_srpms.sh).
# tmt pushes the repo into the container; build-repos.sh rebuilds binary
# RPMs from the SRPMs for the target distro, creates four local repos,
# then runs tc11 and tc12 in sequence.

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"
        setup_distro_environment
    rlPhaseEnd

    rlPhaseStartTest "NVR priority and version selection"
        rlRun "tmt run -i $run --scratch -vvv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name" \
            0 "Run NVR priority tests"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
