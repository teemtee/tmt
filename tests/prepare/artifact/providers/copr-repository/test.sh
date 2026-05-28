#!/bin/bash
# Example test for copr-repository artifact provider
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1
. ../../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"

        setup_distro_environment
    rlPhaseEnd

    while IFS= read -r image; do
        if ! is_fedora "$image" && ! is_centos "$image"; then
            # Can only test rpm artifacts right now
            continue
        fi

        phase_prefix="$(test_phase_prefix $image)"

        rlPhaseStartTest "$phase_prefix Test copr-repository provider with command-line override"
            rlRun "tmt run -i $run --scratch -vv --all \
                provision -h $PROVISION_HOW --image $image" 0 "Run with copr-repository provider"
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
