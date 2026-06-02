#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1
. ./lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup "Prepare test environment"
        rlRun "testdir=$(mktemp -d)" 0 "Create test directory"

        build_rpms

        rlRun "cp -a install-cases $testdir/data" 0 "Copy test data"
        rlRun "cp -a rpms $testdir/data/" 0 "Copy rpms data"
        rlRun "pushd $testdir/data" 0 "Enter test directory"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"

        setup_distro_environment
    rlPhaseEnd

xfail_plans=(
    "/verified-artifacts/pre-installed"
)

    while IFS= read -r image; do
        if ! is_fedora "$image" && ! is_centos "$image"; then
            # Can only test rpm artifacts right now
            continue
        fi

        extra_env=""
        if is_centos_7 "$image"; then
             extra_env="-e DNF_CMD=yum"
            # TODO: centos7 is hard
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

        for plan in $(tmt plans ls); do
            xfail=""
            expected_result=0
            for check_pattern in ${xfail_plans[@]}; do
                if [[ "$plan" =~ $check_pattern ]]; then
                    xfail="(XFAIL)"
                    expected_result=2
                    break
                fi
            done
            rlPhaseStartTest "$phase_prefix $plan $xfail"
                rlRun "tmt run $extra_env -i $run --scratch -vvv --all \
                    plan --name $plan \
                    provision -h $PROVISION_HOW --image $image" \
                    $expected_result "Run test case $plan $xfail"
            rlPhaseEnd
        done
    done <<< "$IMAGES"


    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run $testdir" 0 "Remove temporary files directories"
    rlPhaseEnd
rlJournalEnd
