#!/bin/bash
# Example test for file artifact provider
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1
. ../../lib/common.sh || exit 1

# Detect architecture
ARCH=$(uname -m)

# Remote URL uses cowsay (noarch package)
REMOTE_RPM_URL="https://kojipkgs.fedoraproject.org/packages/cowsay/3.8.4/3.fc43/noarch/cowsay-3.8.4-3.fc43.noarch.rpm"
# Local file uses figlet (arch-specific package)
LOCAL_RPM_URL="https://kojipkgs.fedoraproject.org/packages/figlet/2.2.5/32.20151018gita565ae1.fc43/${ARCH}/figlet-2.2.5-32.20151018gita565ae1.fc43.${ARCH}.rpm"

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"
        rlRun "rpm_dir=$(mktemp -d)" 0 "Create local RPM directory"

        setup_distro_environment

        # Download an RPM file for local file test
        rlRun "curl -L -o $rpm_dir/figlet.rpm $LOCAL_RPM_URL" 0 "Download RPM for local test"

        # Download multiple RPMs into a directory for directory test using dnf download
        # Using different packages (jq and nano) to test directory functionality
        rlRun "multi_rpm_dir=$(mktemp -d)" 0 "Create directory for multiple RPMs"
        rlRun "dnf download --destdir=$multi_rpm_dir jq nano" 0 "Download jq and nano RPMs using dnf"
    rlPhaseEnd

    rlPhaseStartTest "Test file provider with remote URL, local RPM, and directory with multiple RPMs"
        rlRun "tmt run -i $run --scratch -vv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --how artifact --provide file:$REMOTE_RPM_URL --provide file:$rpm_dir/figlet.rpm --provide file:$multi_rpm_dir" 0 "Run with file provider (URL + local RPM + directory)"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run $rpm_dir $multi_rpm_dir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
