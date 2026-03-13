#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../../artifact/lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "data_dir=\$(mktemp -d)" 0 "Create temp data directory"

        setup_distro_environment

        # Fetch the latest koji build ID for make dynamically
        get_koji_build_id "make" "f\${fedora_release}"

        # Copy plan data and substitute the dynamic build ID
        rlRun "cp -r data/. \$data_dir/" 0 "Copy test data"
        rlRun "sed -i 's/KOJI_BUILD_ID/${KOJI_BUILD_ID}/g' \$data_dir/main.fmf" 0 "Substitute koji build ID"
        rlRun "pushd \$data_dir"
    rlPhaseEnd

    rlPhaseStartTest "Test successful verification"
        rlLog "Verify that package from artifact repository passes verification"

        rlRun -s "tmt run -i \$run/success --scratch -vvv --all \
            plan --name /plan/success \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/\$image_name" 0 "Run verification test with correct repo"

        rlAssertGrep "pass .* / make" $rlRun_LOG
        rlAssertGrep "pass .* / make-devel" $rlRun_LOG
        rlAssertGrep "pass .* / diffutils" $rlRun_LOG
        rlAssertGrep "All packages verified successfully." $rlRun_LOG
        rlAssertGrep "1 test passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test verification failure"
        rlLog "Verify that plugin processes all packages and then fails with wrong repo"

        rlRun -s "tmt run -i \$run/failure --scratch -vvv --all \
            plan --name /plan/failure \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/\$image_name" 2 "Verification should fail with wrong repo"

        rlAssertGrep "5 packages" $rlRun_LOG
        rlAssertGrep "pass .* / make" $rlRun_LOG
        rlAssertGrep "pass .* / diffutils" $rlRun_LOG
        rlAssertGrep "fail .* / make-devel" $rlRun_LOG
        rlAssertGrep "expected repo 'SOME_NON_EXISTENT_REPO'" $rlRun_LOG
        rlAssertGrep "actual 'tmt-artifact-shared'" $rlRun_LOG
        rlAssertGrep "fail .* / random-non-existent-package" $rlRun_LOG
        rlAssertGrep "random-non-existent-package.*not installed" $rlRun_LOG
        rlAssertGrep "fail .* / bash" $rlRun_LOG
        rlAssertNotGrep "All packages verified successfully." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf \$run \$data_dir" 0 "Removing run and data directories"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
