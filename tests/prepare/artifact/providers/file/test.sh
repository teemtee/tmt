#!/bin/bash
# Example test for file artifact provider
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1
. ../../lib/common.sh || exit 1

# Detect architecture
ARCH=$(uname -m)

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"
        rlRun "rpm_dir=$(mktemp -d)" 0 "Create local RPM directory"

        setup_distro_environment

        # Choose a tag – change to 'rawhide' or e.g. 'f44' for newer packages if desired
        TAG="f43"

        # 1. REMOTE URL (noarch) ---
        COWSAY_NVR=$(koji latest-pkg "$TAG" cowsay --quiet | awk '{print $1}')
        if [ -z "$COWSAY_NVR" ]; then
            rlFail "Failed to find latest cowsay in tag $TAG"
            exit 1
        fi

        # Construct URL: Parses NVR (Name-Version-Release) and assembles Koji URL
        # Regex explanation: ^(.*)-([^-]+)-([^-]+)$ captures Name, Version, Release
        REMOTE_RPM_URL=$(echo "$COWSAY_NVR" | sed -E "s|^(.*)-([^-]+)-([^-]+)$|https://kojipkgs.fedoraproject.org/packages/\1/\2/\3/noarch/&.noarch.rpm|")

        rlLog "Using cowsay URL: $REMOTE_RPM_URL"

        # 2. LOCAL FILE (arch-specific) ---
        FIGLET_NVR=$(koji latest-pkg "$TAG" figlet --quiet | awk '{print $1}')
        if [ -z "$FIGLET_NVR" ]; then
            rlFail "Failed to find latest figlet in tag $TAG"
            exit 1
        fi

        # Construct URL using current $ARCH
        LOCAL_RPM_URL=$(echo "$FIGLET_NVR" | sed -E "s|^(.*)-([^-]+)-([^-]+)$|https://kojipkgs.fedoraproject.org/packages/\1/\2/\3/${ARCH}/&.${ARCH}.rpm|")

        rlLog "Using figlet URL: $LOCAL_RPM_URL"
        rlRun "curl -L -o $rpm_dir/figlet.rpm $LOCAL_RPM_URL" 0 "Download figlet RPM for local test"

        rlRun "multi_rpm_dir=$(mktemp -d)" 0 "Create directory for multiple RPMs"
        # Use $fedora_release (set by setup_distro_environment) to ensure packages
        rlRun "dnf download --forcearch=$ARCH --releasever=$fedora_release --destdir=$multi_rpm_dir boxes fortune-mod" 0 "Download boxes and fortune-mod RPMs using dnf"
    rlPhaseEnd

    rlPhaseStartTest "Test file provider with remote URL, local RPM, and directory with multiple RPMs"
        rlRun "tmt run -i $run --scratch -vvv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --how artifact --provide file:$REMOTE_RPM_URL --provide file:$rpm_dir/figlet.rpm --provide file:$multi_rpm_dir" 0 "Run with file provider (URL + local RPM + directory)"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run $rpm_dir $multi_rpm_dir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
