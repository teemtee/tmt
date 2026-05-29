#!/bin/bash
# Example test for using multiple artifact providers together
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1
. ../../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        setup_distro_environment
    rlPhaseEnd

    while IFS= read -r image; do
        if ! is_fedora_rawhide "$image"; then
            # Running only against rawhide right now due to hard-coded pattern
            # TODO(#4941): Make this run more generically
            continue
        fi

        phase_prefix="$(test_phase_prefix $image)"

        rlPhaseStartTest "Test multiple providers with command-line override"
            get_koji_build_id "make" "rawhide"
            rlRun "tmt run -i $run --scratch -vv --all \
                provision -h $PROVISION_HOW --image $image \
                prepare --how artifact \
                    --provide koji.build:$KOJI_BUILD_ID \
                    --provide repository-file:file://test-bar.repo" 0 "Run with multiple providers"
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
