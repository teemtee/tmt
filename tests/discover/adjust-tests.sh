#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt run -i $run discover plans --name /fmf/adjust-tests"
        # If we ever change the path...
        tests_yaml="$(find $run -name tests.yaml)"
        rlAssertExits "$tests_yaml"
        rlRun -s "yq '.[].require' < $tests_yaml"
        rlAssertGrep "foo" "$rlRun_LOG"
        rlRun -s "yq '.[].duration' < $tests_yaml"
        # Note the space before 10.. duration is adjusted to the raw input ' 10h'
        rlAssertGrep " 10h" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
