#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    function check_duration() {
        local result_file=$1
        local test_name=$2

        rlRun "yq -ery '.[] | select(.name == \"$test_name\") | .duration | test(\"^[0-9]{2,}:[0-5][0-9]:[0-5][0-9]$\")' $result_file" \
            0 "duration is in HH:MM:SS format"
    }

    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    for verbosity in '' '-dv' '-ddvv' '-dddvvv'; do
        rlPhaseStartTest "Run $verbosity"
            rlRun "tmt run $verbosity --scratch --id $run" 2 "Run all plans"
        rlPhaseEnd
    done

    # NOTE: regular expressions below are slightly less trivial. The
    # order of keys in results.yaml is not fixed, if parser decides,
    # they may swap positions, therefore expressions try to match a
    # *multiline section* of results.yaml that should include test and
    # whatever we're grepping for. Non-greedy matching is used to limit
    # to just a single result in results.yaml, otherwise grep might not
    # reveal a `result` key missing in a particular results because it'd
    # exist in the *next* result in the file.

    rlPhaseStartTest "Check shell results"
        results="$run/plan/shell/execute/results.yaml"

        rlRun "yq -ery '.[] | select(.name == \"/test/shell/good\" and .result == \"pass\")' $results" 0 "Check pass"
        check_duration "$results" "/test/shell/good"

        rlRun "yq -ery '.[] | select(.name == \"/test/shell/weird\" and .result == \"error\")' $results" 0 "Check error"
        check_duration "$results" "/test/shell/weird"

        rlRun "yq -ery '.[] | select(.name == \"/test/shell/bad\" and .result == \"fail\")' $results" 0 "Check fail"
        check_duration "$results" "/test/shell/bad"

        # Check log file exists
        rlRun "yq -ery '.[] | select(.name == \"/test/shell/good\") | .log | .[] | test(\"^data/.+/output.txt$\")' $results" \
            0 "Check output.txt log exists in $results"
    rlPhaseEnd

    rlPhaseStartTest "Check beakerlib results"
        results="$run/plan/beakerlib/execute/results.yaml"

        rlRun "yq -ery '.[] | select(.name == \"/test/beakerlib/good\" and .result == \"pass\")' $results" 0 "Check pass"
        check_duration "$results" "/test/beakerlib/good"

        rlRun "yq -ery '.[] | select(.name == \"/test/beakerlib/need\" and .result == \"warn\")' $results" 0 "Check warn"
        check_duration "$results" "/test/beakerlib/need"

        rlRun "yq -ery '.[] | select(.name == \"/test/beakerlib/weird\" and .result == \"error\")' $results" 0 "Check error"
        check_duration "$results" "/test/beakerlib/weird"

        rlRun "yq -ery '.[] | select(.name == \"/test/beakerlib/bad\" and .result == \"fail\")' $results" 0 "Check fail"
        check_duration "$results" "/test/beakerlib/bad"

        # Check log files exist
        rlRun "yq -ery '.[] | select(.name == \"/test/beakerlib/good\") | .log | map({path: .}) | .[] | select(.path | test(\"^data/.+/output.txt$\"))' $results" \
            0 "Check output.txt log exists in $results"
        rlRun "yq -ery '.[] | select(.name == \"/test/beakerlib/good\") | .log | map({path: .}) | .[] | select(.path | test(\"^data/.+/journal.txt$\"))' $results" \
            0 "Check journal.txt log exists in $results"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
