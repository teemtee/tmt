#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)"
    rlPhaseEnd

    rlPhaseStartTest "Adjust all tests (adjust-tests key)"
        rlRun -s "tmt -c trigger=commit run --scratch -i $run discover plans --name /fmf/adjust-tests"
        # If we ever change the path...
        tests_yaml="$(find $run -name tests.yaml)"
        rlAssertExists "$tests_yaml"
        rlRun -s "yq '.[].require' < $tests_yaml"
        rlAssertGrep "foo" "$rlRun_LOG"
        rlRun -s "yq '.[].duration' < $tests_yaml"
        # 'duration_to_seconds' takes care of injection the default '5m' as the base
        rlAssertGrep "*2" "$rlRun_LOG"
        # check added
        rlRun -s "yq '.[].check' < $tests_yaml"
        rlAssertGrep "avc" $rlRun_LOG
        # recommend should not contain FAILURE
        rlRun -s "yq '.[].recommend' < $tests_yaml"
        rlAssertNotGrep "FAILURE" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Adjust individual tests"
        rlRun -s "tmt run --scratch -i $run discover plans --name /fmf/adjust-individual-tests"
        # If we ever change the path...
        tests_yaml="$(find $run -name tests.yaml)"
        rlAssertExists "$tests_yaml"
        # First one has the adjust
        rlRun -s "yq '.[] | select(.name == \"/tests/discover1\").duration' < $tests_yaml"
        rlAssertGrep "*2" "$rlRun_LOG"
        # Other tests have no adjust
        rlRun -s "yq '.[] | select(.name != \"/tests/discover1\").duration' < $tests_yaml"
        rlAssertNotGrep "*2" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
