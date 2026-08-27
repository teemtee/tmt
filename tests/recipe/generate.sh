#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        recipe="$run/recipe.yaml"
    rlPhaseEnd

    function compare_recipe () {
        local expected="$1"
        # Replace the run root to match the expected recipe.
        temp_recipe=$(mktemp)
        yq '.run.root = "/path/to/fmf_root"' "$recipe" > "$temp_recipe"
        mv "$temp_recipe" "$recipe"
        # Compare recipe content.
        rlRun "yq -o json 'sort_keys(..)' \"$recipe\" > $run/actual_normalized_recipe.json"
        rlRun "yq -o json 'sort_keys(..)' \"$expected\" > $run/expected_normalized_recipe.json"
        rlRun "diff $run/actual_normalized_recipe.json $run/expected_normalized_recipe.json"
    }

    for plan_name in 'local' 'remote' 'minimal'; do
        rlPhaseStartTest "Test recipe generation of a $plan_name plan"
            rlRun -s "tmt -vv run --scratch --id $run -e RUN_ENV=run_value plan -n /plans/$plan_name"
            rlAssertExists "$recipe" "Recipe file exists"
            compare_recipe "$plan_name.yaml"
        rlPhaseEnd
    done

    rlPhaseStartTest "Test recipe generation of a plan with inserted discover step"
        rlRun -s "tmt -vv run --scratch --id $run -e RUN_ENV=run_value --all discover --insert -h fmf plan -n /plans/insert"
        rlAssertExists "$recipe" "Recipe file exists"
        compare_recipe insert.yaml
    rlPhaseEnd

    rlPhaseStartTest "Test recipe generation of an imported plan"
        rlRun -s "tmt -vv run --scratch --id $run -e RUN_ENV=run_value discover plan -n /plans/import"
        rlAssertExists "$recipe" "Recipe file exists"
        compare_recipe import.yaml
    rlPhaseEnd

    rlPhaseStartTest "Test recipe generation after rerun"
        rlRun -s "tmt -vv -c distro=fedora run --scratch --id $run -e RUN_ENV=run_value plan -n /plans/local"
        rlRun -s "tmt -vv run --id $run report --how=html"
        rlAssertExists "$recipe" "Recipe file exists"
        compare_recipe rerun.yaml
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
