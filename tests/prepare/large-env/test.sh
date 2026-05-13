#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "IMAGE_MODE=${IMAGE_MODE:-yes}"

        if [ "$IMAGE_MODE" = "yes" ]; then
            rlRun "IMAGES='$TEST_IMAGE_MODE_IMAGES'"

        elif [ "$PROVISION_HOW" = "container" ]; then
            rlRun "IMAGES="

        elif [ "$PROVISION_HOW" = "virtual" ]; then
            rlRun "IMAGES="

        else
            rlRun "IMAGES="
        fi

        rlRun "run=\$(mktemp -d -p /var/tmp)" 0 "Create run directory"

        # Generate a ~67KB base64 string simulating an encoded secret.
        # This exceeds ARG_MAX when multiplied across Containerfile RUN
        # directives (the bug), but is small enough to pass through
        # individual SSH execute() calls.
        rlRun "python3 -c 'import base64; print(\"LARGE_SECRET: \" + base64.b64encode(b\"x\" * 50000).decode())' > \$run/large-env.yaml"
        rlRun "rlLogInfo \"LARGE_SECRET size: \$(wc -c < \$run/large-env.yaml) bytes\""

        rlRun "pushd data"
        rlRun "export TMT_BOOT_TIMEOUT=300"
        rlRun "export TMT_CONNECT_TIMEOUT=300"
    rlPhaseEnd

    while IFS= read -r image; do
        phase_prefix="$(test_phase_prefix "$image")"

        rlPhaseStartTest "$phase_prefix Prepare/install with large environment"
            rlRun -s "tmt -vvv run --scratch -i \$run --environment-file \$run/large-env.yaml provision --how $PROVISION_HOW --image $image"

            rlAssertGrep "building container image" $rlRun_LOG
            rlAssertGrep "switching to new image" $rlRun_LOG
            rlAssertGrep "rebooting to apply new image" $rlRun_LOG
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf \$run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
