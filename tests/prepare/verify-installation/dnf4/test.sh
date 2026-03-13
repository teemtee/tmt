#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        build_container_image "centos/stream10/upstream:latest"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test successful verification on dnf4"
        rlLog "Verify packages installed from BaseOS and Docker CE repo pass verification"

        rlRun -s "tmt run -i \$run/success --scratch -vvv --all \
            plan --name /plan/success \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/centos/stream10/upstream:latest" \
            0 "Run verification test with correct repos"

        rlAssertGrep "pass .* / make" $rlRun_LOG
        rlAssertGrep "pass .* / diffutils" $rlRun_LOG
        rlAssertGrep "pass .* / docker-ce-cli" $rlRun_LOG
        rlAssertGrep "All packages verified successfully." $rlRun_LOG
        rlAssertGrep "1 test passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test verification failure on dnf4"
        rlLog "Verify wrong repo and missing package fail verification"

        rlRun -s "tmt run -i \$run/failure --scratch -vvv --all \
            plan --name /plan/failure \
            provision -h \$PROVISION_HOW --image \$TEST_IMAGE_PREFIX/centos/stream10/upstream:latest" \
            2 "Verification should fail with wrong repo"

        rlAssertGrep "4 packages" $rlRun_LOG
        rlAssertGrep "pass .* / diffutils" $rlRun_LOG
        rlAssertGrep "pass .* / docker-ce-cli" $rlRun_LOG
        rlAssertGrep "fail .* / make" $rlRun_LOG
        rlAssertGrep "expected repo 'SOME_NON_EXISTENT_REPO'" $rlRun_LOG
        rlAssertGrep "actual 'baseos'" $rlRun_LOG
        rlAssertGrep "fail .* / random-non-existent-package" $rlRun_LOG
        rlAssertGrep "random-non-existent-package.*not installed" $rlRun_LOG
        rlAssertNotGrep "All packages verified successfully." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf \$run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
