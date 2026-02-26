#!/bin/bash
# Outer beakerlib test for the nvr-debug suite.
#
# Builds SRPMs from rpm-data/*.spec using mock, then rebuilds binary RPMs
# using rpmbuild. Both are pushed into the container by tmt. build-repos.sh
# creates local repos from the pre-built RPMs. The artifact provider
# (repository-file) installs the relevant .repo files before each TC runs.

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        SCRIPT_DIR="$(dirname $0)"
        SRPM_DIR="$SCRIPT_DIR/data/srpms"
        rlRun "mkdir -p '$SRPM_DIR'"
        for spec in "$SCRIPT_DIR"/rpm-data/*.spec; do
            rlRun "sudo mock --buildsrpm --spec '$spec' --sources '$SCRIPT_DIR/rpm-data/' \
                --resultdir '$SRPM_DIR' --enable-network" 0 "Build SRPM from $spec"
        done
        PACKAGE="dummy-nvr-test"
        BUILD_DIR="$(mktemp -d)"
        for srpm in "$SRPM_DIR"/${PACKAGE}-*.src.rpm; do
            rlRun "rpmbuild --define '_topdir $BUILD_DIR' --rebuild '$srpm'" 0 "Build binary RPM from $srpm"
        done
        rlRun "mkdir -p '$SCRIPT_DIR/data/rpms'"
        rlRun "cp '$BUILD_DIR'/RPMS/noarch/${PACKAGE}-*.rpm '$SCRIPT_DIR/data/rpms/'"
        rlRun "rm -rf '$BUILD_DIR'"
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"
        DATA_DIR="$(pwd)"
        setup_distro_environment
    rlPhaseEnd

    rlPhaseStartTest "TC 1.1 - Repository priority overrides package version"
        rlRun "tmt run -i $run --scratch -vvv --all \
            plan --name /plan-tc11 \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --insert --how artifact \
                --provide 'repository-file:file://$DATA_DIR/tc11-high.repo' \
                --provide 'repository-file:file://$DATA_DIR/tc11-low.repo'" \
            0 "TC1.1: high-priority repo (priority=30) wins over newer package"
    rlPhaseEnd

    rlPhaseStartTest "TC 1.2 - Same priority falls back to NVR comparison"
        rlRun "tmt run -i $run --scratch -vvv --all \
            plan --name /plan-tc12 \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --insert --how artifact \
                --provide 'repository-file:file://$DATA_DIR/tc12-a.repo' \
                --provide 'repository-file:file://$DATA_DIR/tc12-b.repo'" \
            0 "TC1.2: same-priority repos, highest NVR (v2.0) wins"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove run directory"
        rlRun "rm -rf '$SCRIPT_DIR/data/rpms'" 0 "Remove pre-built RPMs"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
