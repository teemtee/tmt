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
    # Intentionally should fail at install or verify stage
    # TODO: Check the failure more narrowly
    "^/broken/verified-artifacts"
    # Same failure like the dnf4, but the explicit --best flag does not need to be included (#5090)
    # Interestingly `/verified-artifacts/obsoletes/basic/downgrade` does not fail, it seems it does not
    # read the other repo metadata there, but things may change in the future
    "^/verified-artifacts/obsoletes/pre-installed/downgrade"
)
xfail_plans_nobest=(
    # On dnf4 these plans fail because of the intrinsic --best flag passed (#5090)
    # Missing ^ here is intetional, to cover both /broken/available-artifacts and /available-artifacts
    "/available-artifacts/obsoletes/pre-installed/downgrade/with-devel$"
    "^/broken/available-artifacts/basic"
    "^/broken/available-artifacts/obsoletes/basic"
    "^/broken/available-artifacts/.*pre-installed/.*/with-devel$"
    "^/broken/no-artifacts/.*/pre-installed/with-devel$"
    "^/broken/no-artifacts/obsoletes/basic$"
    "^/broken/no-artifacts/upgrade/with-devel$"
)
xfail_centos6_centos7=(
    # yum cannot downgrade a pre-installed package
    "/pre-installed/downgrade/with-devel$"
    "^/verified-artifacts/pre-installed/downgrade/only-foo$"
)
complicated_centos7=(
    # Obsoletes wins over priority. Some of these tests pass when they should xfail
    # some fail in different ways, it is hard to handle them all consistently, so just skip them.
    "^/verified-artifacts/obsoletes/basic/downgrade$"
    "^/available-artifacts/obsoletes/basic/downgrade$"
    "^/available-artifacts/obsoletes/pre-installed/downgrade/with-devel$"
    "^/broken/available-artifacts/obsoletes/basic/downgrade$"
    "^/broken/available-artifacts/obsoletes/pre-installed/downgrade/with-devel$"
)
complicated_centos6=(
    # Obsoletes wins over priority. Some of these tests pass when they should xfail
    # some fail in different ways, it is hard to handle them all consistently, so just skip them.
    "^/verified-artifacts/obsoletes/basic/downgrade$"
    "^/available-artifacts/obsoletes/basic/downgrade$"
    "^/available-artifacts/obsoletes/pre-installed/downgrade/with-devel$"
    "^/broken/available-artifacts/obsoletes/basic/downgrade$"
    "^/broken/available-artifacts/obsoletes/pre-installed/downgrade/with-devel$"
    # el6 yum promotes local foo-1.4 install to foo-ng via Obsoletes (el7 skips
    # that for YumLocalPackage), so the expected pre-installed foo-1.4 is never present.
    "^/no-artifacts/obsoletes/pre-installed/only-foo$"
    "^/broken/no-artifacts/obsoletes/pre-installed/only-foo$"
)

    while IFS= read -r image; do
        if ! is_fedora "$image" && ! is_centos "$image"; then
            # Can only test rpm artifacts right now
            continue
        fi

        extra_env=""
        if is_centos_7 "$image" || is_centos_6 "$image"; then
             extra_env="-e DNF_CMD=yum"
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
            if is_centos_7 "$image" || is_centos_6 "$image" || is_centos_stream_9 "$image" || is_centos_stream_10 "$image" || is_fedora_eln "$image"; then
                for check_pattern in ${xfail_plans_nobest[@]}; do
                    if [[ "$plan" =~ $check_pattern ]]; then
                        xfail="(XFAIL)"
                        expected_result=2
                        break
                    fi
                done
            fi
            xfail_distro=()
            complicated_distro=()
            if is_centos_7 "$image"; then
                xfail_distro=("${xfail_centos6_centos7[@]}")
                complicated_distro=("${complicated_centos7[@]}")
            elif is_centos_6 "$image"; then
                xfail_distro=("${xfail_centos6_centos7[@]}")
                complicated_distro=("${complicated_centos6[@]}")
            fi
            for check_pattern in ${xfail_distro[@]}; do
                if [[ "$plan" =~ $check_pattern ]]; then
                    xfail="(XFAIL)"
                    expected_result=2
                    break
                fi
            done
            # Skip too complicated situations altogether
            unset complicated
            for check_pattern in ${complicated_distro[@]}; do
                if [[ "$plan" =~ $check_pattern ]]; then
                    complicated=1
                    break
                fi
            done
            if [[ -n "$complicated" ]]; then
                continue
            fi
            rlPhaseStartTest "$phase_prefix $plan $xfail"
                rlRun "tmt run $extra_env -i $run --scratch -vvv --all \
                    plan --name '^$plan$' \
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
