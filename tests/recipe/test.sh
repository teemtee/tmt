#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        recipe="$run/recipe.yaml"
        expected_recipe="recipe.yaml"
    rlPhaseEnd

    function replace_values () {
        temp_recipe=$(mktemp)
        yq '.run.root = "/fmf_root_path" | .plans[]."environment-from-intrinsics".TMT_VERSION = "version"' "$recipe" > "$temp_recipe"
        mv "$temp_recipe" "$recipe"
        sed -i "s#$run#/run_path#g" "$recipe"
    }

    rlPhaseStartTest "Test recipe generation"
        rlRun -s "tmt -vv run --id $run -e RUN_ENV=value"
        rlAssertExists "$recipe" "Recipe file exists"
        replace_values
        rlAssertEquals "Generated recipe matches expected recipe" "$(yq -S . "$recipe")" "$(yq -S . "$expected_recipe")"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
