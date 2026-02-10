#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Basic container provision"
        rlRun -s "tmt run --id $run -vvv"
        rlAssertGrep "NAME.*Fedora Linux" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Environment variables passed to container"
        # Test that environment variables are passed to podman run via --env-file
        rlRun -s "tmt run --scratch --id $run -avvv \
            -e TMT_TEST_VAR=hello_from_tmt \
            -e TMT_ANOTHER_VAR=with_value \
            provision -h container -i fedora \
            execute -h tmt -s 'echo TMT_TEST_VAR=\$TMT_TEST_VAR; echo TMT_ANOTHER_VAR=\$TMT_ANOTHER_VAR'"

        # Verify the --env-file flag is passed to podman run
        rlAssertGrep "\-\-env-file" $rlRun_LOG

        # Verify the environment file was created with correct content
        env_file=$(find $run -name 'podman-run-environment' | head -1)
        rlAssertExists "$env_file"
        rlAssertGrep "TMT_TEST_VAR=hello_from_tmt" "$env_file"
        rlAssertGrep "TMT_ANOTHER_VAR=with_value" "$env_file"

        # Verify the environment variables are available in the container
        rlAssertGrep "TMT_TEST_VAR=hello_from_tmt" $rlRun_LOG
        rlAssertGrep "TMT_ANOTHER_VAR=with_value" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Environment variables with newlines are skipped"
        # Test that environment variables containing newlines are skipped with a warning
        # Using $'...' syntax to embed actual newline in the value
        rlRun -s "tmt run --scratch --id $run -avvv \
            -e TMT_NORMAL_VAR=normal_value \
            -e TMT_NEWLINE_VAR=\$'line1\nline2' \
            provision -h container -i fedora \
            execute -h tmt -s 'echo TMT_NORMAL_VAR=\$TMT_NORMAL_VAR; echo TMT_NEWLINE_VAR=\$TMT_NEWLINE_VAR'"

        # Verify the warning is emitted for the variable with newline
        rlAssertGrep "TMT_NEWLINE_VAR.*contains a newline character" $rlRun_LOG
        rlAssertGrep "skipping this variable" $rlRun_LOG

        # Verify the environment file does NOT contain the newline variable
        env_file=$(find $run -name 'podman-run-environment' | head -1)
        rlAssertExists "$env_file"
        rlAssertGrep "TMT_NORMAL_VAR=normal_value" "$env_file"
        rlAssertNotGrep "TMT_NEWLINE_VAR" "$env_file"

        # Verify only the normal variable is available in the container
        rlAssertGrep "TMT_NORMAL_VAR=normal_value" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
