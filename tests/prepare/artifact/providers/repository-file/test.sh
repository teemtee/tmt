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
        build_rpm "bar"

        # Stage the locally-built 'bar' RPM so it is synced to the guest and
        # can be turned into a local repository for CentOS 7 (see main.fmf)
        rlRun "mkdir -p local-repo" 0 "Create local repo staging directory"
        rlRun "cp $LIB_DIR/../rpms/bar/bar-1.0-1.noarch.rpm local-repo/" 0 "Stage bar RPM"
    rlPhaseEnd

    while IFS= read -r image; do
        if ! is_fedora "$image" && ! is_centos "$image"; then
            # Can only test rpm artifacts right now
            continue
        fi

        distro="other"
        if is_centos_7 "$image"; then
            distro="centos-7"
        fi

        phase_prefix="$(test_phase_prefix $image)"

        rlPhaseStartTest "$phase_prefix Test repository-file provider"
            rlRun "tmt -c distro=$distro run -i $run --scratch -vvv --all \
                provision -h $PROVISION_HOW --image $image" \
                0 "Run with repository-file provider"
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -rf $run local-repo"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
