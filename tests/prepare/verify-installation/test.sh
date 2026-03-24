#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        . ../artifact/lib/common.sh || exit 1

        setup_distro_environment
        rlRun "image=\$TEST_IMAGE_PREFIX/\$image_name"

        rlRun "data_dir=\$(mktemp -d)" 0 "Create temp data directory"

        # FIXME: https://github.com/teemtee/tmt/issues/4742
        # Both distros use Fedora koji - the koji.build provider always reads
        # the default 'koji' profile which points to Fedora koji.
        # Fedora-built diffstat (1.68) is newer than CentOS baseos (1.66)
        # so the artifact version is always preferred on both distros.
        get_koji_build_id "diffstat" "f\${fedora_release:-43}"

        if rlIsFedora; then
            rlRun "cp -r data-fedora/. \$data_dir/" 0 "Copy test data"
        elif rlIsCentOS; then
            rlRun "cp -r data-centos/. \$data_dir/" 0 "Copy test data"
        else
            rlDie "Unsupported distribution, must be Fedora or CentOS"
        fi
        rlRun "sed -i 's/KOJI_BUILD_ID/${KOJI_BUILD_ID}/g' \$data_dir/main.fmf" 0 "Substitute koji build ID"
        rlRun "pushd \$data_dir"
    rlPhaseEnd

    rlPhaseStartTest "Test successful verification"
        rlRun -s "tmt run -i \$run/success --scratch -vvv --all \
            plan --name /plan/success \
            provision -h \$PROVISION_HOW --image \$image" \
            0 "Run verification test with correct repos"

        rlAssertGrep "pass .* / diffstat" $rlRun_LOG
        rlAssertGrep "pass .* / make" $rlRun_LOG
        rlAssertGrep "pass .* / diffutils" $rlRun_LOG
        rlAssertGrep "All packages verified successfully." $rlRun_LOG
        rlAssertNotGrep "Package source verification failed for:" $rlRun_LOG
        rlAssertGrep "1 test passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test verification failure"
        rlRun -s "tmt run -i \$run/failure --scratch -vvv --all \
            plan --name /plan/failure \
            provision -h \$PROVISION_HOW --image \$image" \
            2 "Verification should fail with wrong repo"

        rlAssertGrep "4 packages" $rlRun_LOG
        rlAssertGrep "pass .* / make" $rlRun_LOG
        rlAssertGrep "pass .* / diffutils" $rlRun_LOG
        rlAssertGrep "fail .* / diffstat" $rlRun_LOG
        rlAssertGrep "actual 'tmt-artifact-shared'" $rlRun_LOG
        rlAssertGrep "expected repo 'SOME_NON_EXISTENT_REPO'" $rlRun_LOG
        rlAssertGrep "fail .* / random-non-existent-package" $rlRun_LOG
        rlAssertGrep "random-non-existent-package.*not installed" $rlRun_LOG
        rlAssertGrep "Package source verification failed for:" $rlRun_LOG
        rlAssertNotGrep "All packages verified successfully." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf \$run \$data_dir" 0 "Removing run and data directories"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
