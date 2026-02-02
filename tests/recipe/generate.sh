#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        recipe="$run/recipe.yaml"
    rlPhaseEnd

    function replace_values () {
        temp_recipe=$(mktemp)
        yq '.run.root = "/path/to/fmf_root" | .plans[]."environment-from-intrinsics".TMT_VERSION = "version"' "$recipe" > "$temp_recipe"
        mv "$temp_recipe" "$recipe"
        sed -i "s#$run#/run_path#g" "$recipe"
    }

    for plan_name in 'simple' 'remote'; do
        rlPhaseStartTest "Test recipe generation of a $plan_name plan"
            rlRun -s "tmt -vv run --scratch --id $run -e RUN_ENV=run_value plan -n /plans/$plan_name"
            rlAssertExists "$recipe" "Recipe file exists"
            replace_values
            rlRun "yq 'sort_keys(..)' \"$recipe\" > $run/actual_normalized_recipe.yaml"
            rlRun "yq 'sort_keys(..)' \"$plan_name.yaml\" > $run/expected_normalized_recipe.yaml"
            rlRun "diff $run/actual_normalized_recipe.yaml $run/expected_normalized_recipe.yaml"
        rlPhaseEnd
    done

    rlPhaseStartTest "Test recipe generation of an imported plan"
        rlRun -s "tmt -vv run --scratch --id $run -e RUN_ENV=run_value discover plan -n /plans/import"
        rlAssertExists "$recipe" "Recipe file exists"
        replace_values
        rlRun "yq 'sort_keys(..)' \"$recipe\" > $run/actual_normalized_recipe.yaml"
        rlRun "yq 'sort_keys(..)' import.yaml > $run/expected_normalized_recipe.yaml"
        rlRun "diff $run/actual_normalized_recipe.yaml $run/expected_normalized_recipe.yaml"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
