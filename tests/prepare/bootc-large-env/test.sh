#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d --tmpdir=/var/tmp/tmt)" 0 "Create run directory"

        # Generate a ~67KB base64 string simulating an encoded secret.
        # This exceeds ARG_MAX when multiplied across Containerfile RUN
        # directives (the bug), but is small enough to pass through
        # individual SSH execute() calls.
        rlRun "python3 -c 'import base64; print(\"LARGE_SECRET: \" + base64.b64encode(b\"x\" * 50000).decode())' > large-env.yaml"
        rlRun "echo \"LARGE_SECRET size: \$(wc -c < large-env.yaml) bytes\""
    rlPhaseEnd

    rlPhaseStartTest "Prepare/shell with large environment on bootc guest"
        rlRun -s "tmt -dddvvv run --scratch -i \$run --environment-file large-env.yaml plan --name /plans/centos-stream-10/large-env"

        # Verify the prepare/shell command was collected
        rlAssertGrep "Collected command for Containerfile" \$rlRun_LOG

        # Verify the container image was built
        rlAssertGrep "building container image" \$rlRun_LOG

        # Verify bootc switch was called
        rlAssertGrep "switching to new image" \$rlRun_LOG

        # Verify reboot happened
        rlAssertGrep "rebooting to apply new image" \$rlRun_LOG

        # Verify tree --version ran successfully in the test
        rlAssertGrep "tree v" \$rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf \$run" 0 "Remove run directory"
        rlRun "rm -f large-env.yaml" 0 "Remove generated environment file"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
