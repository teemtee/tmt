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

        # Get koji build info
        rlRun -s "koji list-tagged --latest f${fedora_release} make" 0 "Get the latest make build"
        if [[ ! "$(tail -1 $rlRun_LOG)" =~ ^([^[:space:]]+) ]]; then
            rlDie "Package NVR regex failed"
        fi
        rlRun "make_nvr=${BASH_REMATCH[1]}" 0 "Get the package NVR"
        rlRun -s "koji buildinfo $make_nvr" 0 "Get the build info"
        if [[ ! "$(head -1 $rlRun_LOG)" =~ ^BUILD:[[:space:]]*[^[:space:]]+[[:space:]]*\[([[:digit:]]+)\] ]]; then
            rlDie "BuildID regex failed"
        fi
        rlRun "make_buildid=${BASH_REMATCH[1]}" 0 "Get the make build ID"

        # Download a local RPM for file provider
        rlRun "dnf download --destdir=$test_dir make 2>&1" 0 "Download make RPM"
        rlRun "rpm_file=\$(ls $test_dir/*.rpm | head -1)" 0 "Get RPM file path"
        rlLog "Using RPM file: $rpm_file"

        # Create a repository .repo file
        rlRun "cat > $test_dir/test-fedora.repo << EOF
[test-fedora]
name=Test Fedora Repository
baseurl=https://download.fedoraproject.org/pub/fedora/linux/releases/$fedora_release/Everything/\\\$basearch/os/
enabled=1
gpgcheck=0
EOF"
        rlRun "repo_url=file://$test_dir/test-fedora.repo"
    rlPhaseEnd

    rlPhaseStartTest "Test all providers together"
        rlRun "tmt run -i $run --scratch -avvv \
            --environment REPO_LIST=tmt-artifact-shared,test-fedora \
            --environment ARTIFACT_LIST=make \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/fedora/${fedora_release}:latest \
            prepare --insert --how artifact \
                --provide koji.build:$make_buildid \
                --provide file:$rpm_file \
                --provide repository-url:$repo_url" \
            0 "Test multiple providers together (koji + file + repository-url)"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run $test_dir" 0 "Removing run and test directories"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
