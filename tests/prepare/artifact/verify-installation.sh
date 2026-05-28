#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1
. lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd verify-installation"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        setup_distro_environment
        build_rpm "bar"
    rlPhaseEnd

    while IFS= read -r image; do
        if ! is_fedora "$image" && ! is_centos "$image"; then
            # Can only test rpm artifacts right now
            continue
        fi

        phase_prefix="$(test_phase_prefix $image)"

        rlPhaseStartTest "$phase_prefix Test verify-installation phase injection (verify=true)"
            rlRun -s "tmt run -i $run --scratch -vvv --all \
                plan --name /plan \
                provision -h $PROVISION_HOW --image $image" \
                0 "Verify should pass with verify=true (default)"

            rlAssertGrep "verify-artifact-packages" $rlRun_LOG
            rlAssertGrep "pass verify-artifact-packages / make" $rlRun_LOG
            rlAssertGrep "All packages verified successfully" $rlRun_LOG
        rlPhaseEnd

        rlPhaseStartTest "$phase_prefix verify=false suppresses verify-installation phase"
            rlRun -s "tmt run -i $run --scratch -vvv --all \
                plan --name /plan \
                provision -h $PROVISION_HOW --image $image \
                prepare --update --name artifact --no-verify" \
                0 "No-verify should succeed without verify phase"

            rlAssertNotGrep "verify-artifact-packages" $rlRun_LOG
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
