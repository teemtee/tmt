#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "test_dir=\$(mktemp -d)" 0 "Create test directory for local artifacts"
        if ! rlIsFedora; then
          # TODO: Handle centos artifacts also
          rlDie "Skipping because non-fedora test is not implemented"
        fi
        rlRun "fedora_release=43"
        build_container_image "fedora/${fedora_release}:latest"

        # Get koji build info for later tests
        rlRun -s "koji list-tagged --latest f${fedora_release} make" 0 "Get the latest make build"
        # The NVR should be the first word in the last line:
        # make-4.4.1-10.fc42                        f42                   releng
        if [[ ! "$(tail -1 $rlRun_LOG)" =~ ^([^[:space:]]+) ]]; then
            rlDie "Package NVR regex failed"
        fi
        rlRun "make_nvr=${BASH_REMATCH[1]}" 0 "Get the package NVR"
        rlRun -s "koji buildinfo $make_nvr" 0 "Get the build info"
        # The build ID should be in square brackets of the first line:
        # BUILD: make-4.4.1-10.fc42 [2625600]
        if [[ ! "$(head -1 $rlRun_LOG)" =~ ^BUILD:[[:space:]]*[^[:space:]]+[[:space:]]*\[([[:digit:]]+)\] ]]; then
            rlDie "BuildID regex failed"
        fi
        rlRun "make_buildid=${BASH_REMATCH[1]}" 0 "Get the make build ID"

        # Download a local RPM for file provider
        # Download the same make package we're using for koji tests to ensure consistency
        # dnf download needs just the package name, not the full NVR
        rlRun "dnf download --destdir=$test_dir make 2>&1" 0 "Download make RPM"
        rlRun "rpm_file=\$(ls $test_dir/*.rpm | head -1)" 0 "Get RPM file path"
        rlLog "Using RPM file: $rpm_file"
    rlPhaseEnd

    rlPhaseStartTest "Test all providers together"
        # TODO: Handle VM, local and other provision also
        rlRun "tmt run -i $run --scratch -av \
            --environment TEST_REPO_NAME=docker-ce-stable \
            --environment ARTIFACT_LIST=make \
            --environment REPO_LIST=tmt-artifact-shared,docker-ce-stable \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare --insert --how artifact \
                --provide koji.build:$make_buildid \
                --provide file:$rpm_file \
                --provide repository-url:https://download.docker.com/linux/fedora/docker-ce.repo" \
            0 "Test the providers together (koji + file + repository-url)"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run $test_dir" 0 "Removing run and test directories"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
