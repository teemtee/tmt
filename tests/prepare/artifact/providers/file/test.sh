#!/bin/bash
# Example test for file artifact provider
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../../images.sh || exit 1
. ../../lib/common.sh || exit 1

# Detect architecture
ARCH=$(uname -m)

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"

        setup_distro_environment
        build_rpm "bar"
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

        rlPhaseStartTest "$phase_prefix Test file provider"
            # Remote rpm taken from https://copr.fedorainfracloud.org/coprs/lecris/_tmt_test/
            # TODO: get this more dynamically https://github.com/fedora-copr/copr/issues/4119
            rlRun "REMOTE_RPM_URL=https://packages.redhat.com/api/pulp-content/public-copr/lecris/_tmt_test/fedora-rawhide-x86_64/Packages/b/bar-1.0-1.noarch.rpm"

            rlRun "tmt run -i $run --scratch -vvv --all \
                provision -h $PROVISION_HOW --image $image \
                prepare --how artifact --provide file:$REMOTE_RPM_URL" \
                0 "Run remote file"
            rlRun "tmt run -i $run --scratch -vvv --all \
                provision -h $PROVISION_HOW --image $image \
                prepare --how artifact --provide file:$LIB_DIR/../rpms/bar/bar-1.0-1.rpm" \
                0 "Run absolute file path"
            rlRun "tmt run -i $run --scratch -vvv --all \
                provision -h $PROVISION_HOW --image $image \
                prepare --how artifact --provide file:../../rpms/bar/bar-1.0-1.rpm" \
                0 "Run relative file path"
            rlRun "tmt run -i $run --scratch -vvv --all \
                provision -h $PROVISION_HOW --image $image \
                prepare --how artifact --provide file:../../../rpms/bar/bar-*.rpm" \
                0 "Run glob pattern"
            rlRun "tmt run -i $run --scratch -vvv --all \
                provision -h $PROVISION_HOW --image $image \
                prepare --how artifact --provide file:$LIB_DIR/../rpms/bar" \
                0 "Run directory"
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -rf $run $rpm_dir $multi_rpm_dir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
