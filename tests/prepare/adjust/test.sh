#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"

        rlRun "output=\$(mktemp)" 0 "Create output file"
        rlRun "pushd data"
        rlRun "set -o pipefail"

        build_container_image "centos/7/upstream\:latest"
        build_container_image "ubi/8/upstream\:latest"
    rlPhaseEnd

    for plan in without defined; do
        for test in without defined; do
            # Skip when both/none define required packages
            [[ $plan == $test ]] && continue
            for image in $TEST_IMAGE_PREFIX/centos/7/upstream:latest $TEST_IMAGE_PREFIX/ubi/8/upstream:latest; do
                rlPhaseStartTest "Test: Plan $plan, test $test, image $distro"
                    if [ "$image" = "$TEST_IMAGE_PREFIX/centos/7/upstream:latest" ]; then
                        distro="centos-7"
                    else
                        distro="centos-stream-8"
                    fi
                    cmd="tmt -c distro=${distro} run -arvvv "
                    cmd+="provision -h container -i $image "
                    cmd+="plan --name $plan test --name $test "
                    cmd+="2>&1 | tee $output"
                    rlRun "$cmd"
                    rlAssertGrep 'out: Smoke test for yaml' $output
                    if [[ $image == "$TEST_IMAGE_PREFIX/ubi/8/upstream:latest" ]]; then
                        rlAssertGrep 'python3-yaml' $output
                        rlAssertNotGrep 'PyYAML' $output
                    else
                        rlAssertGrep 'PyYAML' $output
                        rlAssertNotGrep 'python3-yaml' $output
                    fi
                rlPhaseEnd
            done
        done
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $output" 0 "Remove output file"
    rlPhaseEnd
rlJournalEnd
