#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Sanity"
        tmt="tmt -vv test export"

        rlRun "$tmt --policy ../policies/test/test.yaml /basic"
        rlRun -s "$tmt --policy ../policies/test/test.yaml /basic 2> /dev/null | yq -cSr '.[] | .test'"
        rlAssertEquals \
            "Verify that test key is modified" \
            "$(cat $rlRun_LOG)" \
            "bash -c 'echo \"Spiked test.\"; /bin/true'"

        rlRun "$tmt --policy ../policies/test/test.yaml /full"
        rlRun -s "$tmt --policy ../policies/test/test.yaml /full 2> /dev/null | yq -cSr '.[] | .test'"
        rlAssertEquals \
            "Verify that test key is modified" \
            "$(cat $rlRun_LOG)" \
            "bash -c 'echo \"Spiked test.\"; /bin/true'"

        rlRun "$tmt --policy ../policies/test/contact.yaml /basic"
        rlRun -s "$tmt --policy ../policies/test/contact.yaml /basic 2> /dev/null | yq -cSr '.[] | .contact'"
        rlAssertEquals \
            "Verify that contact key is modified" \
            "$(cat $rlRun_LOG)" \
            "[\"xyzzy\"]"

        rlRun "$tmt --policy ../policies/test/contact.yaml /full"
        rlRun -s "$tmt --policy ../policies/test/contact.yaml /full 2> /dev/null | yq -cSr '.[] | .contact'"
        rlAssertEquals \
            "Verify that contact key is modified" \
            "$(cat $rlRun_LOG)" \
            "[\"foo\",\"baz\"]"

        rlRun "$tmt --policy ../policies/test/environment.yaml /basic"
        rlRun -s "$tmt --policy ../policies/test/environment.yaml /basic 2> /dev/null | yq -cSr '.[] | .environment'"
        rlAssertEquals \
            "Verify that environment key is modified" \
            "$(cat $rlRun_LOG)" \
            "{\"FOO\":\"xyzzy\"}"

        rlRun "$tmt --policy ../policies/test/environment.yaml /full"
        rlRun -s "$tmt --policy ../policies/test/environment.yaml /full 2> /dev/null | yq -cSr '.[] | .environment'"
        rlAssertEquals \
            "Verify that environment key is modified" \
            "$(cat $rlRun_LOG)" \
            "{\"FOO\":\"baz\",\"QUX\":\"QUUX\"}"

        rlRun "$tmt --policy ../policies/test/check.yaml /basic"
        rlRun -s "$tmt --policy ../policies/test/check.yaml /basic 2> /dev/null | yq -cSr '.[] | .check | [.[] | {how, result}]'"
        rlAssertEquals \
            "Verify that check key is modified" \
            "$(cat $rlRun_LOG)" \
            "[{\"how\":\"avc\",\"result\":\"respect\"}]"

        rlRun "$tmt --policy ../policies/test/check.yaml /full"
        rlRun -s "$tmt --policy ../policies/test/check.yaml /full 2> /dev/null | yq -cSr '.[] | .check  | [.[] | {how, result}]'"
        rlAssertEquals \
            "Verify that check key is modified" \
            "$(cat $rlRun_LOG)" \
            "[{\"how\":\"avc\",\"result\":\"info\"},{\"how\":\"dmesg\",\"result\":\"respect\"}]"
    rlPhaseEnd

    rlPhaseStartTest "Test VALUE_SOURCE usage"
        tmt="tmt -vv test export"

        rlRun "$tmt --policy ../policies/test/duration.yaml /value-source/default-duration"
        rlRun -s "$tmt --policy ../policies/test/duration.yaml /value-source/default-duration 2> /dev/null | yq -cSr '.[] | .duration'"
        rlAssertEquals \
            "Verify that no custom value is recognized" \
            "$(cat $rlRun_LOG)" \
            "5m +30m +50m"

        rlRun "$tmt --policy ../policies/test/duration.yaml /value-source/custom-duration"
        rlRun -s "$tmt --policy ../policies/test/duration.yaml /value-source/custom-duration 2> /dev/null | yq -cSr '.[] | .duration'"
        rlAssertEquals \
            "Verify that custom value is recognized" \
            "$(cat $rlRun_LOG)" \
            "5m +5m +10m +50m"

        rlRun "$tmt --policy ../policies/test/duration.yaml /value-source/same-as-default"
        rlRun -s "$tmt --policy ../policies/test/duration.yaml /value-source/same-as-default 2> /dev/null | yq -cSr '.[] | .duration'"
        rlAssertEquals \
            "Verify that custom value which is the same as the default is recognized" \
            "$(cat $rlRun_LOG)" \
            "5m +10m +50m"
    rlPhaseEnd

    rlPhaseStartTest "Run"
        rlRun -s "tmt --feeling-safe -vv run --id $run --policy ../policies/test/test.yaml discover provision -h local execute report -h display -vvv plan --default test --name /basic"

        rlAssertGrep "content: Spiked test." $rlRun_LOG
        rlAssertEquals \
            "Verify that test has been modified" \
            "$(yq -cSr '.[] | .test' $run/default/plan/discover/tests.yaml)" \
            "bash -c 'echo \"Spiked test.\"; /bin/true'"
    rlPhaseEnd

    rlPhaseStartTest "Invalid keys"
        rlRun -s "tmt -vv test export --policy ../policies/test/invalid.yaml /basic" 2
        rlAssertGrep "Could not find field 'script' in class '/basic'." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
