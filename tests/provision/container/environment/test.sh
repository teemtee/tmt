#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Environment variables passed to container"
        # Test that environment variables are passed to podman run via --env-file
        rlRun -s "tmt run --id $run --before cleanup -dddvvv -e TMT_TEST_VAR=hello_from_tmt"

        # Verify the --env-file flag is passed to podman run
        ENV_FILE="$run/plan/provision/default-0/podman-run-environment"
        rlAssertGrep "Podman run environment file written to '$ENV_FILE'." $rlRun_LOG
        rlAssertGrep "podman run.*--env-file $ENV_FILE" $rlRun_LOG

        # Check the contents of the podman run environment file
        rlAssertExists "$ENV_FILE"
        rlAssertGrep "TMT_TEST_VAR=hello_from_tmt" "$ENV_FILE"
        rlAssertNotGrep "TMT_NEWLINE_VAR" "$ENV_FILE"

        # Verify the warning is emitted for the variable with newline
        rlAssertGrep "TMT_NEWLINE_VAR.*contains a newline character" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "tmt run --id $run cleanup"
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
