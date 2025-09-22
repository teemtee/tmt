#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        recipe="$run/recipe.yaml"
    rlPhaseEnd

    function check_run_env () {
        if ! yq -e -r '.run.environment.RUN_ENV' "$recipe" > /dev/null 2>&1; then
            rlFail "Run environment is not correct"
        else
            rlPass "Run environment is correct"
        fi
    }

    function check_plan_env () {
        if ! yq -e '.plans[0] | select(.environment.PLAN_ENV != null and (.environment | has("RUN_ENV") | not))' "$recipe" > /dev/null; then
            rlFail "Plan environment is not correct"
        else
            rlPass "Plan environment is correct"
        fi
    }

    function check_test_env () {
        if ! yq -e '.plans[0].discover.tests[0] | select(.environment.TEST_ENV != null and (.environment | has("PLAN_ENV") | not))' "$recipe" > /dev/null; then
            rlFail "Test environment is not correct"
        else
            rlPass "Test environment is correct"
        fi
    }

    rlPhaseStartTest "Test recipe generation"
        rlRun -s "tmt -vv run --id $run -e RUN_ENV=value"
        recipe="$run/recipe.yaml"
        rlAssertExists "$recipe" "Recipe file exists"
        rlAssertGrep "results-path: plan/execute/results.yaml" "$recipe"
        check_run_env
        check_plan_env
        check_test_env
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
