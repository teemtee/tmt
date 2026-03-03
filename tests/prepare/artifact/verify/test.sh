#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        setup_distro_environment

        # Get koji build ID for make
        get_koji_build_id "make" "f${fedora_release}"

        # Replace placeholder in main.fmf with actual koji build ID
        rlRun "sed -i 's/DUMMY_KOJI_BUILD_ID/'\$KOJI_BUILD_ID'/g' main.fmf" 0 "Replace koji build ID placeholder"
    rlPhaseEnd

    rlPhaseStartTest "Test successful verification"
        rlLog "Verify that package from artifact repository passes verification"

        rlRun -s "tmt run -i \$run/success --scratch -vvv --all \
            plan --name /plan/success \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/\$image_name 2>&1" 0 "Run verification test with correct repo"

        rlAssertGrep "All packages verified successfully" $rlRun_LOG
        rlAssertGrep "1 test passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test verification failure"
        rlLog "Verify that plugin processes all packages and then fails with wrong repo"

        rlRun -s "tmt run -i \$run/failure --scratch -vvv --all \
            plan --name /plan/failure \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/\$image_name 2>&1" 2 "Verification should fail with wrong repo"

        rlAssertGrep "Verifying 3 package(s) came from expected repositories" $rlRun_LOG
        rlAssertGrep "Package source verification failed" $rlRun_LOG
        rlAssertGrep "make-devel" $rlRun_LOG
        rlAssertGrep "Expected: 'SOME_NON_EXISTENT_REPO'" $rlRun_LOG
        rlAssertGrep "Actual:   'tmt-artifact-shared'" $rlRun_LOG
        rlAssertGrep "Package source verification failed for 1 package" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf \$run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
