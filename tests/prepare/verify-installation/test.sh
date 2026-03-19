#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        if rlIsFedora; then
            build_container_image "fedora/43/upstream:latest"
            rlRun "image=\$TEST_IMAGE_PREFIX/fedora/43/upstream:latest"
            rlRun "pushd data-fedora"
        else
            build_container_image "centos/stream10/upstream:latest"
            rlRun "image=\$TEST_IMAGE_PREFIX/centos/stream10/upstream:latest"
            rlRun "pushd data-centos"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Test successful verification"
        rlRun -s "tmt run -i \$run/success --scratch -vvv --all \
            plan --name /plan/success \
            provision -h \$PROVISION_HOW --image \$image" \
            0 "Run verification test with correct repos"

        rlAssertGrep "2 packages" $rlRun_LOG
        rlAssertGrep "pass .* / diffutils" $rlRun_LOG

        if rlIsFedora; then
            rlAssertGrep "pass .* / patch" $rlRun_LOG
        else
            rlAssertGrep "pass .* / make" $rlRun_LOG
        fi

        rlAssertGrep "All packages verified successfully." $rlRun_LOG
        rlAssertNotGrep "Package source verification failed for:" $rlRun_LOG
        rlAssertGrep "1 test passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test verification failure"
        rlRun -s "tmt run -i \$run/failure --scratch -vvv --all \
            plan --name /plan/failure \
            provision -h \$PROVISION_HOW --image \$image" \
            2 "Verification should fail with wrong repo"

        rlAssertGrep "3 packages" $rlRun_LOG

        rlAssertGrep "pass .* / diffutils" $rlRun_LOG
        rlAssertGrep "fail .* / make" $rlRun_LOG

        if ! rlIsFedora; then
            rlAssertGrep "actual 'baseos'" $rlRun_LOG
        fi

        rlAssertGrep "expected repo 'SOME_NON_EXISTENT_REPO'" $rlRun_LOG
        rlAssertGrep "fail .* / random-non-existent-package" $rlRun_LOG
        rlAssertGrep "random-non-existent-package.*not installed" $rlRun_LOG
        rlAssertGrep "Package source verification failed for:" $rlRun_LOG
        rlAssertNotGrep "All packages verified successfully." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf \$run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
