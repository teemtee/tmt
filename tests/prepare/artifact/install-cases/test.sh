#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup "Prepare test environment"
        PROVISION_HOW=${PROVISION_HOW:-container}
        rlRun "testdir=$(mktemp -d)" 0 "Create test directory"
        rlRun "cp -a data $testdir" 0 "Copy test data"
        rlRun "pushd $testdir/data" 0 "Enter test directory"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"
        setup_distro_environment
    rlPhaseEnd

    rlPhaseStartSetup "Build RPM repos"
        for repo_dir in rpms/*; do
            rlRun "pushd $repo_dir"
            rlRun "rpmbuild --define='_topdir build' -bb *.spec" 0 "Build rpms"
            rlRun "cp build/RPMS/*/* ./" 0 "Move rpms next to spec file"
            rlRun "popd"
        done
    rlPhaseEnd

xfail_plans=(
   "/verified-artifacts/pre-installed"
)

    for plan in $(tmt plans ls); do
        xfail=""
        expected_result=0
        for check_pattern in ${xfail_plans[@]}; do
            if [[ "$plan" =~ $check_pattern ]]; then
                xfail="(XFAIL)"
                expected_result=1
                break
            fi
        done
        rlPhaseStartTest "$plan $xfail"
            rlRun "tmt run -i $run --scratch -vvv --all \
                plan --name $plan \
                provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name" \
                $expected_result "Run test case $plan $xfail"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run $testdir" 0 "Remove temporary files directories"
    rlPhaseEnd
rlJournalEnd
