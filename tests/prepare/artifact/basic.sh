#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1
. lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd basic"
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

        rlPhaseStartTest "$phase_prefix Test artifact installation"
            rlRun "tmt run -i $run --scratch -vvv --all \
                provision -h $PROVISION_HOW --image $image" \
                0 "Run tmt with artifact providers"
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
