#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        if rlIsFedora; then
            . ../artifact/lib/common.sh || exit 1

            setup_distro_environment
            rlRun "image=\$TEST_IMAGE_PREFIX/\$image_name"

            rlRun "data_dir=\$(mktemp -d)" 0 "Create temp data directory"

            # Fetch the latest koji build ID for make dynamically
            get_koji_build_id "make" "f\${fedora_release}"

            # Copy plan data and substitute the dynamic build ID
            rlRun "cp -r data-fedora/. \$data_dir/" 0 "Copy test data"
            rlRun "sed -i 's/KOJI_BUILD_ID/${KOJI_BUILD_ID}/g' \$data_dir/main.fmf" 0 "Substitute koji build ID"
            rlRun "pushd \$data_dir"
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

        # make and diffutils are available in both Fedora and CentOS
        rlAssertGrep "pass .* / make" $rlRun_LOG
        rlAssertGrep "pass .* / diffutils" $rlRun_LOG

        if rlIsFedora; then
            rlAssertGrep "pass .* / make-devel" $rlRun_LOG
        else
            rlAssertGrep "pass .* / centpkg" $rlRun_LOG
        fi

        rlAssertGrep "All packages verified successfully." $rlRun_LOG
        rlAssertGrep "1 test passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test verification failure"
        rlRun -s "tmt run -i \$run/failure --scratch -vvv --all \
            plan --name /plan/failure \
            provision -h \$PROVISION_HOW --image \$image" \
            2 "Verification should fail with wrong repo"

        # diffutils passes on both distros in the failure plan
        rlAssertGrep "pass .* / diffutils" $rlRun_LOG

        rlAssertGrep "4 packages" $rlRun_LOG
        if rlIsFedora; then
            rlAssertGrep "pass .* / make" $rlRun_LOG
            rlAssertGrep "fail .* / make-devel" $rlRun_LOG
            rlAssertGrep "actual 'tmt-artifact-shared'" $rlRun_LOG
        else
            rlAssertGrep "pass .* / centpkg" $rlRun_LOG
            rlAssertGrep "fail .* / make" $rlRun_LOG
            rlAssertGrep "actual 'baseos'" $rlRun_LOG
        fi

        rlAssertGrep "expected repo 'SOME_NON_EXISTENT_REPO'" $rlRun_LOG
        rlAssertGrep "fail .* / random-non-existent-package" $rlRun_LOG
        rlAssertGrep "random-non-existent-package.*not installed" $rlRun_LOG
        rlAssertNotGrep "All packages verified successfully." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        if rlIsFedora; then
            rlRun "rm -rf \$run \$data_dir" 0 "Removing run and data directories"
        else
            rlRun "rm -rf \$run" 0 "Removing run directory"
        fi
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
