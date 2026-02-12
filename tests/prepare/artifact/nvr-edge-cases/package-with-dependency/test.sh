#!/bin/bash
# Test NVR edge cases when dependencies ARE present in the shared repository
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1
. ../../lib/common.sh || exit 1

# Force x86_64 architecture
ARCH=x86_64

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"

        setup_distro_environment

        rlRun "rpm_dir=$(mktemp -d)" 0 "Create directory for RPMs"
        # Use $fedora_release (set by setup_distro_environment) to ensure packages match test distro
        rlRun "dnf download --forcearch=$ARCH --releasever=$fedora_release --destdir=$rpm_dir --resolve --alldeps jq nano" 0 "Download jq and nano RPMs with all dependencies"
    rlPhaseEnd

    rlPhaseStartTest "Test provider NVR edge case for packages with dependencies"
        rlRun "tmt run -i $run --scratch -vvv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --how artifact --provide file:$rpm_dir" 0 "Run with file provider (packages with dependencies)"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run $rpm_dir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
