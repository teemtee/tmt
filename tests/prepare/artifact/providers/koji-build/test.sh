#!/bin/bash
# Example test for koji.build artifact provider
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1
. ../../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "run_av=\$(mktemp -d)" 0 "Create run directory for auto_verify test"
        rlRun "run_nv=\$(mktemp -d)" 0 "Create run directory for no-auto-verify test"

        setup_distro_environment

        # Get koji build ID for make
        get_koji_build_id "make" "f${fedora_release}"

        # Create a substituted copy of the data dir for plan-based tests
        rlRun "data_dir=\$(mktemp -d)" 0 "Create temp data directory"
        rlRun "cp -r . \$data_dir/" 0 "Copy test data"
        rlRun "sed -i 's/DUMMY_KOJI_BUILD_ID/${KOJI_BUILD_ID}/g' \$data_dir/main.fmf" \
            0 "Substitute koji build ID"
    rlPhaseEnd

    rlPhaseStartTest "Test koji.build provider with command-line override"
        rlRun "tmt run -i $run --scratch -vvv --all \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --how artifact --provide koji.build:$KOJI_BUILD_ID" 0 "Run with koji.build provider"
    rlPhaseEnd

    rlPhaseStartTest "Test auto-inject of verify-installation phase (auto_verify=true)"
        rlRun -s "( cd \$data_dir && tmt run -i \$run_av --scratch -vvv --all \
            plan --name /plan/auto-verify \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/\$image_name )" \
            0 "Auto-verify should pass with auto_verify=true (default)"

        rlAssertGrep "verify-artifact-packages" $rlRun_LOG
        rlAssertGrep "pass verify-artifact-packages / make" $rlRun_LOG
        rlAssertGrep "All packages verified successfully" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test auto_verify=false suppresses auto-inject"
        rlRun -s "( cd \$data_dir && tmt run -i \$run_nv --scratch -vvv --all \
            plan --name /plan/no-verify \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/\$image_name )" \
            0 "No-auto-verify should succeed without verify phase"

        rlAssertNotGrep "verify-artifact-packages" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf \$run \$run_av \$run_nv \$data_dir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
