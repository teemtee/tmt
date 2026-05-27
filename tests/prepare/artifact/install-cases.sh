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

)

    while IFS= read -r image; do
        if ! is_fedora "$image" && ! is_centos "$image"; then
            # Can only test rpm artifacts right now
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
                rlRun "tmt run -i $run --scratch -vvv --all \
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
