#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1
. ../artifact/lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        setup_distro_environment
    rlPhaseEnd

    rlPhaseStartTest "Test successful verification"
        rlLog "Verify that package from artifact repository passes verification"

        rlRun -s "tmt run -i \$run/success --scratch -vvv --all \
            plan --name /plan/success \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/\$image_name 2>&1" 0 "Run verification test with correct repo"

        rlAssertGrep "All packages verified successfully." $rlRun_LOG
        rlAssertGrep "1 test passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test verification failure"
        rlLog "Verify that plugin processes all packages and then fails with wrong repo"

        rlRun -s "tmt run -i \$run/failure --scratch -vvv --all \
            plan --name /plan/failure \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/\$image_name 2>&1" 2 "Verification should fail with wrong repo"

        rlAssertGrep "3 packages" $rlRun_LOG
        rlAssertGrep "fail make-devel" $rlRun_LOG
        rlAssertGrep "expected repo 'SOME_NON_EXISTENT_REPO'" $rlRun_LOG
        rlAssertGrep "actual 'tmt-artifact-shared'" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf \$run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
