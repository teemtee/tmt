#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Sanity"
        function run_test () {
            local policy="$1"
            local plan="$2"
            local filter="$3"
            local expected="$4"

            rlRun -s "tmt -vv test export --policy-file ../policies/test/$1 $plan"
            rlAssertGrep "Apply tmt policy '../policies/test/$1' to tests." $rlRun_LOG

            rlRun -s "tmt -vv test export --policy-file ../policies/test/$1 $plan 2> /dev/null | yq -cSr '.[] | $filter'"

            rlAssertEquals \
                "Verify that $(echo "$filter" | cut -d' ' -f1) key is modified" \
                "$(cat $rlRun_LOG)" \
                "$expected"
        }

        run_test test.yaml /basic .test "bash -c 'echo \"Spiked test.\"; /bin/true'"
        run_test test.yaml /full  .test "bash -c 'echo \"Spiked test.\"; /bin/true'"

        run_test contact.yaml /basic .contact "[\"xyzzy\"]"
        run_test contact.yaml /full  .contact "[\"foo\",\"baz\"]"

        run_test environment.yaml /basic .environment "{\"FOO\":\"xyzzy\"}"
        run_test environment.yaml /full  .environment "{\"FOO\":\"baz\",\"QUX\":\"QUUX\"}"

        run_test check.yaml /basic '.check | [.[] | {how, result}]' "[{\"how\":\"avc\",\"result\":\"respect\"}]"
        run_test check.yaml /full  '.check | [.[] | {how, result}]' "[{\"how\":\"avc\",\"result\":\"info\"},{\"how\":\"dmesg\",\"result\":\"respect\"}]"
    rlPhaseEnd

    rlPhaseStartTest "Test VALUE_SOURCE usage"
        function run_test () {
            local message="$1"
            local plan="$2"
            local expected="$3"

            rlRun    "tmt -vv test export --policy-file ../policies/test/duration.yaml $plan"
            rlRun -s "tmt -vv test export --policy-file ../policies/test/duration.yaml $plan 2> /dev/null | yq -cSr '.[] | .duration'"

            rlAssertEquals \
                "$message" \
                "$(cat $rlRun_LOG)" \
                "$expected"
        }

        run_test "Verify that no custom value is recognized"                               /value-source/default-duration "5m +30m +50m"
        run_test "Verify that custom value is recognized"                                  /value-source/custom-duration  "5m +5m +10m +50m"
        run_test "Verify that custom value which is the same as the default is recognized" /value-source/same-as-default  "5m +10m +50m"
    rlPhaseEnd

    rlPhaseStartTest "Test whether tmt run accepts a policy"
        function run_test () {
            local option="$1"
            local envvar="$2"

            rlRun -s "$envvar tmt --feeling-safe -vv run --id $run --scratch $option discover provision -h local execute report -h display -vvv plan --default test --name /basic"

            rlAssertGrep "content: Spiked test." $rlRun_LOG
            rlAssertEquals \
                "Verify that test has been modified" \
                "$(yq -cSr '.[] | .test' $run/default/plan/discover/tests.yaml)" \
                "bash -c 'echo \"Spiked test.\"; /bin/true'"
        }

        # Test command-line option...
        run_test "--policy-file ../policies/test/test.yaml" ""

        # ... and test also the envvar.
        run_test ""                                         "TMT_POLICY_FILE=../policies/test/test.yaml"
    rlPhaseEnd

    rlPhaseStartTest "Policy root"
        function run_test () {
            local policy_root="$1"
            local policy_file="$2"
            local policy_name="$3"
            local expected_code="$4"
            local expected_error="$5"

            if [ -n "$1" ]; then
                policy_root_option="--policy-root $policy_root"
                policy_root_envvar="TMT_POLICY_ROOT=$policy_root"
            else
                policy_root_option=""
                policy_root_envvar=""
            fi

            if [ -n "$2" ]; then
                policy_file_option="--policy-file $policy_file"
                policy_file_envvar="TMT_POLICY_FILE=$policy_file"
            else
                policy_file_option=""
                policy_file_envvar=""
            fi

            if [ -n "$3" ]; then
                policy_name_option="--policy-name $policy_name"
                policy_name_envvar="TMT_POLICY_NAME=$policy_name"
            else
                policy_name_option=""
                policy_name_envvar=""
            fi

            rlRun -s "tmt --feeling-safe -vv run --id $run --scratch $policy_root_option $policy_file_option $policy_name_option discover provision -h local execute report -h display -vvv plan --default test --name /basic" "$expected_code"
            rlAssertGrep "$expected_error" $rlRun_LOG

            rlRun -s "$policy_root_envvar $policy_file_envvar $policy_name_envvar tmt --feeling-safe -vv run --id $run --scratch discover provision -h local execute report -h display -vvv plan --default test --name /basic" "$expected_code"
            rlAssertGrep "$expected_error" $rlRun_LOG
        }

        run_test /tmp        ../policies/test/test.yaml ""             2 "Policy '/tmp/../policies/test/test.yaml' does not reside under policy root '/tmp'."
        run_test /tmp        test.yaml                  ""             2 "Policy '/tmp/test.yaml' not found."
        run_test /tmp        ""                         test/test      2 "Policy 'test/test' does not point to a file."
        run_test ../policies ""                         does-not-exist 2 "Policy 'does-not-exist' does not point to a file."
        run_test ""          ""                         test/test      2 "Policy can be loaded by its name only when '--policy-root' is specified."
        run_test ""          test/test.yaml             ""             2 "Policy 'test/test.yaml' not found."
        run_test ../policies test/test.yaml             test/test      2 "Options '--policy-name' and '--policy-file' are mutually exclusive."

        run_test ../policies ""                         test/test      0 "content: Spiked test."
        run_test ../policies test/test.yaml             ""             0 "content: Spiked test."
        run_test ""          ../policies/test/test.yaml ""             0 "content: Spiked test."
    rlPhaseEnd

    rlPhaseStartTest "Invalid keys"
        rlRun -s "tmt -vv test export --policy-file ../policies/test/invalid.yaml /basic" 2
        rlAssertGrep "Could not find field 'script' in class '/basic'." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
