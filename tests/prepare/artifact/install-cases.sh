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

    while IFS= read -r image; do
        if ! is_fedora "$image" && ! is_centos "$image"; then
            # Can only test rpm artifacts right now
            continue
        fi

        extra_env=""
        if is_centos_7 "$image"; then
             extra_env="-e DNF_CMD=yum"
        fi

        phase_prefix="$(test_phase_prefix $image)"

        for plan in $(tmt plans ls); do
            xfail=
            if [[ "$plan" =~ "^/broken/verified-artifacts" ]]; then
                # Expected failure because we are explicitly installing a broken package
                xfail=(
                    'stderr:\s+ - nothing provides some-non-existent-package needed by .* from tmt-artifact-shared'
                    'fail: Command .* install -y .* returned 1.'
                )
            elif [[ "$plan" =~ "^/verified-artifacts/obsoletes/pre-installed/downgrade" ]]; then
                # Pre-installed package does not let the install downgrade, so this is expected to fail
                xfail=(
                    'stderr:\s+- installed package foo-ng-1.0-1.noarch obsoletes foo < 3.0-1 provided by foo-1.1-1.noarch from tmt-artifact-shared'
                    'stderr:\s+- conflicting requests'
                    'fail: Command .* install -y .* returned 1.'
                )
            elif is_centos_7 "$image" || is_centos_stream_9 "$image" || is_centos_stream_10 "$image" || is_fedora_eln "$image"; then
                # On CentOS-like images --best flag is set by default so fallback mechanism is not applied and some cases fail
                xfail_plans_nobest=(
                    # Missing ^ here is intetional, to cover both /broken/available-artifacts and /available-artifacts
                    "/available-artifacts/obsoletes/pre-installed/downgrade/with-devel$"
                    "^/broken/available-artifacts/basic"
                    "^/broken/available-artifacts/obsoletes/basic"
                    "^/broken/available-artifacts/.*pre-installed/.*/with-devel$"
                    "^/broken/no-artifacts/.*/pre-installed/with-devel$"
                    "^/broken/no-artifacts/obsoletes/basic$"
                    "^/broken/no-artifacts/upgrade/with-devel$"
                )
                for check_pattern in ${xfail_plans_nobest[@]}; do
                    if [[ "$plan" =~ $check_pattern ]]; then
                        xfail=(
                            'stderr:\s+- cannot install the best candidate for the job'
                            'fail: Command .* install -y .* returned 1.'
                        )
                        break
                    fi
                done
            fi
            if is_centos_7 "$image"; then
                if [[ "$plan" =~ "/pre-installed/downgrade/with-devel$" || "$plan" =~ "^/verified-artifacts/pre-installed/downgrade/only-foo$"  ]]; then
                    # yum cannot downgrade a pre-installed package
                    xfail=(

                    )
                else
                    # Obsoletes wins over priority. Some of these tests pass when they should xfail
                    # some fail in different ways, it is hard to handle them all consistently, so just skip them.
                    complicated_centos7=(
                        "^/verified-artifacts/obsoletes/basic/downgrade$"
                        "^/available-artifacts/obsoletes/basic/downgrade$"
                        "^/available-artifacts/obsoletes/pre-installed/downgrade/with-devel$"
                        "^/broken/available-artifacts/obsoletes/basic/downgrade$"
                        "^/broken/available-artifacts/obsoletes/pre-installed/downgrade/with-devel$"
                        "^/verified-artifacts/obsoletes/basic/downgrade$"
                    )
                    # Skip too complicated situations altogether
                    unset complicated
                    for check_pattern in ${complicated_centos7[@]}; do
                        if [[ "$plan" =~ $check_pattern ]]; then
                            complicated=1
                            break
                        fi
                    done
                    if [[ -n "$complicated" ]]; then
                        continue
                    fi
                fi
            fi
            expected_result=$(( 0${xfail:+2} ))
            rlPhaseStartTest "$phase_prefix $plan ${xfail:+(XFAIL)}"
                rlRun -s "tmt run $extra_env -i $run --scratch -vvv --all \
                    plan --name '^$plan$' \
                    provision -h $PROVISION_HOW --image $image" \
                    $expected_result "Run test case $plan $xfail"
                for xfail_message in "${xfail[@]}"; do
                    rlAssertGrep "$xfail_message" $rlRun_LOG -E
                done
            rlPhaseEnd
        done
    done <<< "$IMAGES"


    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run $testdir" 0 "Remove temporary files directories"
    rlPhaseEnd
rlJournalEnd
