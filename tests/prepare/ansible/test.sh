#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"

        if [ "$PROVISION_HOW" = "container" ]; then
            rlRun "IMAGES='$TEST_CONTAINER_IMAGES'"

            build_container_images

        elif [ "$PROVISION_HOW" = "virtual" ]; then
            rlRun "IMAGES='$TEST_VIRTUAL_IMAGES'"

        else
            rlRun "IMAGES="
        fi

        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
    rlPhaseEnd

    while IFS= read -r image; do
        for plan in "local" "remote"; do
            phase_prefix="$(test_phase_prefix $image) [/$plan]"

            rlPhaseStartTest "$phase_prefix Test Ansible playbook"
                if is_fedora_coreos "$image"; then
                        rlLogInfo "Skipping because of https://github.com/teemtee/tmt/issues/2884: tmt cannot run tests on Fedora CoreOS containers"
                    rlPhaseEnd

                    continue
                fi

                [ "$PROVISION_HOW" = "container" ] && rlRun "podman images $image"

                # Run given method
                if [ "$PROVISION_HOW" = "local" ]; then
                    rlRun "tmt run -i $run --scratch -av provision -h $PROVISION_HOW           plan -n /$plan"
                else
                    rlRun "tmt run -i $run --scratch -av provision -h $PROVISION_HOW -i $image plan -n /$plan"
                fi

                # Verify extra-args were delivered
                rlAssertGrep "ansible-playbook -vvv" "$run/log.txt"

                # After the local provision remove the test file
                if [[ $PROVISION_HOW == local ]]; then
                    rlRun "sudo rm -f /tmp/prepared"
                fi
            rlPhaseEnd
        done
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Removing run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
