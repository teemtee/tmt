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

    rlPhaseStartCleanup
        rlRun "popd"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
