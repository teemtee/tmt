#!/bin/bash
# Example test for repository-file artifact provider
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
        if ! is_fedora "$image" && ! is_centos "$image"; then
            # Can only test rpm artifacts right now
            continue
        fi

        if is_centos_7 "$image"; then
            # TODO(#4941):
            # Centos 7 not supported because of missing provides resolution on `yum`
            continue
        fi

        if is_centos_stream_9 "$image" || is_centos_stream_10 "$image"; then
            # TODO(#4941):
            # dnf repoquery fails
            # - Error: 'Package' object has no attribute 'full_nevra'
            # - Or gives an output of
            #   'bar':
            #    - nevra: '%{full_nevra}'
            #      repo_id: 'tmt-artifact-shared'
            continue
        fi

        phase_prefix="$(test_phase_prefix $image)"

        rlPhaseStartTest "$phase_prefix Test repository-file provider"
            rlRun "tmt run -i $run --scratch -vv --all \
                provision -h $PROVISION_HOW --image $image" \
                0 "Run with repository-file provider"
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
