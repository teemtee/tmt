#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
    rlPhaseEnd

    rlPhaseStartTest
        tmt="tmt --root data -vv test export"

        rlRun -s "$tmt --profile profiles/test/test.yaml /basic 2> /dev/null | yq -cSr '.[] | .test'"
        rlAssertEquals "foo?" "$(cat $rlRun_LOG)" "scl enable gcc-toolset-15 dummy-command"

        rlRun -s "$tmt --profile profiles/test/test.yaml /full 2> /dev/null | yq -cSr '.[] | .test'"
        rlAssertEquals "foo?" "$(cat $rlRun_LOG)" "scl enable gcc-toolset-15 dummy-command"

        rlRun -s "$tmt --profile profiles/test/contact.yaml /basic 2> /dev/null | yq -cSr '.[] | .contact'"
        rlAssertEquals "foo?" "$(cat $rlRun_LOG)" "[\"xyzzy\"]"

        rlRun -s "$tmt --profile profiles/test/contact.yaml /full 2> /dev/null | yq -cSr '.[] | .contact'"
        rlAssertEquals "foo?" "$(cat $rlRun_LOG)" "[\"foo\",\"baz\"]"

        rlRun -s "$tmt --profile profiles/test/environment.yaml /basic 2> /dev/null | yq -cSr '.[] | .environment'"
        rlAssertEquals "foo?" "$(cat $rlRun_LOG)" "{\"FOO\":\"xyzzy\"}"

        rlRun -s "$tmt --profile profiles/test/environment.yaml /full 2> /dev/null | yq -cSr '.[] | .environment'"
        rlAssertEquals "foo?" "$(cat $rlRun_LOG)" "{\"FOO\":\"baz\",\"QUX\":\"QUUX\"}"

        rlRun -s "$tmt --profile profiles/test/check.yaml /basic 2> /dev/null | yq -cSr '.[] | .check | [.[] | {how, result}]'"
        rlAssertEquals "foo?" "$(cat $rlRun_LOG)" "[{\"how\":\"avc\",\"result\":\"respect\"}]"

        rlRun -s "$tmt --profile profiles/test/check.yaml /full 2> /dev/null | yq -cSr '.[] | .check  | [.[] | {how, result}]'"
        rlAssertEquals "foo?" "$(cat $rlRun_LOG)" "[{\"how\":\"avc\",\"result\":\"info\"},{\"how\":\"dmesg\",\"result\":\"respect\"}]"
    rlPhaseEnd

    rlPhaseStartCleanup
    rlPhaseEnd
rlJournalEnd
