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
    rlPhaseEnd

    rlPhaseStartTest "Test verify-installation phase injection (verify=true)"
        rlRun -s "tmt run -i $run --scratch -vvv --all \
            plan --name /plan/verify \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --how artifact --provide koji.build:${KOJI_BUILD_ID}" \
            0 "Verify should pass with verify=true (default)"

        rlAssertGrep "verify-artifact-packages" $rlRun_LOG
        rlAssertGrep "pass verify-artifact-packages / make" $rlRun_LOG
        rlAssertGrep "All packages verified successfully" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test verify=false suppresses verify-installation phase"
        rlRun -s "tmt run -i $run --scratch -vvv --all \
            plan --name /plan/no-verify \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --how artifact --provide koji.build:${KOJI_BUILD_ID} --no-verify" \
            0 "No-verify should succeed without verify phase"

        rlAssertNotGrep "verify-artifact-packages" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
