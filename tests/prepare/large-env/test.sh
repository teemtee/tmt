#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "IMAGE_MODE=${IMAGE_MODE:-yes}"

        # TODO: Enable IMAGES for container and virtual provision methods
        # once the large-env fix is verified for those backends.
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
        rlRun "pushd data"

        # Size the env dynamically so 2 shell prepare steps produce a
        # Containerfile that exceeds MAX_ARG_STRLEN (PAGE_SIZE * 32).
        # Each RUN inlines the full export; raw_bytes * 4/3 (base64) ≈
        # half the limit, so two RUNs combined just exceed it.
        rlRun "max_arg_strlen=\$(( \$(getconf PAGE_SIZE) * 32 ))"
        rlRun "raw_bytes=\$(( max_arg_strlen * 5 / 12 ))"
        rlRun "rlLogInfo \"MAX_ARG_STRLEN: \$max_arg_strlen  raw_bytes: \$raw_bytes\""
        rlRun "python3 -c 'import base64; print(\"LARGE_SECRET: \" + base64.b64encode(b\"x\" * '\$raw_bytes').decode())' > large-env.yaml"
        rlRun "rlLogInfo \"LARGE_SECRET size: \$(wc -c < large-env.yaml) bytes\""

        rlRun "export TMT_BOOT_TIMEOUT=300"
        rlRun "export TMT_CONNECT_TIMEOUT=300"
    rlPhaseEnd

    while IFS= read -r image; do
        phase_prefix="$(test_phase_prefix "$image")"

        rlPhaseStartTest "$phase_prefix Prepare/install with large environment"
            rlRun -s "tmt -vvv run --all --scratch -i \$run --environment-file large-env.yaml provision --how $PROVISION_HOW --image $image"

            rlAssertGrep "building container image" $rlRun_LOG
            rlAssertGrep "switching to new image" $rlRun_LOG
            rlAssertGrep "rebooting to apply new image" $rlRun_LOG
        rlPhaseEnd
    done <<< "$IMAGES"

    rlPhaseStartCleanup
        rlRun "rm -f large-env.yaml" 0 "Remove generated env file"
        rlRun "popd"
        rlRun "rm -rf \$run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
