#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "run=\$(mktemp -d)"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt -c trigger=commit run -i $run discover plans --name /fmf/adjust-tests"
        # If we ever change the path...
        tests_yaml="$(find $run -name tests.yaml)"
        rlAssertExits "$tests_yaml"
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

    rlPhaseStartCleanup
        rlRun "rm -rf $run"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
