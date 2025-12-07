#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd ../shared-data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "test_dir=\$(mktemp -d)" 0 "Create test directory for local artifacts"
        if ! rlIsFedora; then
          # TODO: Handle centos artifacts also
          rlDie "Skipping because non-fedora test is not implemented"
        fi
        rlRun "fedora_release=43"
        build_container_image "fedora/${fedora_release}:latest"

        # Download a local RPM for file provider
        rlRun "dnf download --destdir=$test_dir make 2>&1" 0 "Download make RPM"
        rlRun "rpm_file=\$(ls $test_dir/*.rpm | head -1)" 0 "Get RPM file path"
        rlLog "Using RPM file: $rpm_file"
    rlPhaseEnd

    rlPhaseStartTest "Test file provider"
        rlRun "tmt run -i $run --scratch -avvv \
            --environment REPO_LIST=tmt-artifact-shared \
            --environment ARTIFACT_LIST=make \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare --insert --how artifact --provide file:$rpm_file" \
            0 "Test file provider with local RPM"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run $test_dir" 0 "Removing run and test directories"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
