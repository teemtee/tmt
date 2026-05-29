#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1
. ../artifact/lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"

        setup_distro_environment
        build_rpm "bar"
        rlRun "BAR_RPM=$LIB_DIR/../rpms/bar/*.rpm"
    rlPhaseEnd

    while IFS= read -r image; do
        if ! is_fedora "$image" && ! is_centos "$image"; then
            # Can only test rpm artifacts right now
            continue
        fi

        if is_centos_7 "$image"; then
            # TODO(#4941):
            # Centos 7 not supported because of missing provides resolution on `yum`
            continue
        fi

        phase_prefix="$(test_phase_prefix $image)"

        rlPhaseStartTest "$phase_prefix Test successful verification"
            rlRun -s "tmt run -i $run/success --scratch -vvv --all \
                plan --name /plan/success \
                provision -h $PROVISION_HOW --image $image \
                prepare --insert -h artifact --provide file:$BAR_RPM" \
                0 "Run verification test with correct repos"

            rlAssertGrep "pass .* / bar" $rlRun_LOG

            rlAssertGrep "All packages verified successfully." $rlRun_LOG
            rlAssertNotGrep "Package source verification failed for:" $rlRun_LOG
            rlAssertGrep "1 test passed" $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "$phase_prefix Test verification failure"
            rlRun -s "tmt run -i $run/failure --scratch -vvv --all \
                plan --name /plan/failure \
                provision -h $PROVISION_HOW --image $image \
                prepare --insert -h artifact --provide file:$BAR_RPM" \
                2 "Verification should fail with wrong repo"

            rlAssertGrep "fail .* / bar" $rlRun_LOG
            rlAssertGrep "expected repo 'SOME_NON_EXISTENT_REPO'" $rlRun_LOG
            rlAssertGrep "fail .* / random-non-existent-package" $rlRun_LOG
            rlAssertGrep "random-non-existent-package.*not installed" $rlRun_LOG
            rlAssertGrep "Package source verification failed for:" $rlRun_LOG
            rlAssertNotGrep "All packages verified successfully." $rlRun_LOG
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Removing run and data directories"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
