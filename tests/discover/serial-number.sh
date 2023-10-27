#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "workdir=\$(mktemp -d)" 0 "Create tmp directory"
    rlPhaseEnd

    rlPhaseStartTest "Single discover phase"
        rlRun 'pushd serial-number'
        rlRun "tmt -vv run --scratch --id $workdir discover plan --name '/single-discover'"
        rlRun -s "yq -er '.[] | \"\\(.name) \\(.\"serial-number\")\"' $workdir/plans/single-discover/discover/tests.yaml"
        rlAssertGrep "/tests/bar 1" $rlRun_LOG
        rlAssertGrep "/tests/foo 2" $rlRun_LOG
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Multiple discover phases"
        rlRun 'pushd serial-number'
        rlRun "tmt -vv run --scratch --id $workdir discover plan --name '/multiple-discover'"
        rlRun -s "yq -er '.[] | \"\\(.name) \\(.\"serial-number\")\"' $workdir/plans/multiple-discover/discover/tests.yaml"
        rlAssertGrep "/default-0/tests/bar 1" $rlRun_LOG
        rlAssertGrep "/default-0/tests/foo 2" $rlRun_LOG
        rlAssertGrep "/default-1/tests/bar 3" $rlRun_LOG
        rlAssertGrep "/default-1/tests/foo 4" $rlRun_LOG
        rlAssertGrep "/default-2/tests/bar 5" $rlRun_LOG
        rlAssertGrep "/default-2/tests/foo 6" $rlRun_LOG
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Multiple plans"
        rlRun 'pushd serial-number'
        rlRun "tmt -vv run --scratch --id $workdir discover plan --name '/multiple-plans'"

        rlRun -s "yq -er '.[] | \"\\(.name) \\(.\"serial-number\")\"' $workdir/plans/multiple-plans/plan1/discover/tests.yaml"
        rlAssertGrep "/default-0/tests/bar 1" $rlRun_LOG
        rlAssertGrep "/default-0/tests/foo 2" $rlRun_LOG
        rlAssertGrep "/default-1/tests/bar 3" $rlRun_LOG
        rlAssertGrep "/default-1/tests/foo 4" $rlRun_LOG

        rlRun -s "yq -er '.[] | \"\\(.name) \\(.\"serial-number\")\"' $workdir/plans/multiple-plans/plan2/discover/tests.yaml"
        rlAssertGrep "/tests/bar 1" $rlRun_LOG
        rlAssertGrep "/tests/foo 2" $rlRun_LOG

        rlRun -s "yq -er '.[] | \"\\(.name) \\(.\"serial-number\")\"' $workdir/plans/multiple-plans/plan3/discover/tests.yaml"
        rlAssertGrep "/default-0/tests/bar 1" $rlRun_LOG
        rlAssertGrep "/default-0/tests/foo 2" $rlRun_LOG
        rlAssertGrep "/default-1/tests/bar 3" $rlRun_LOG
        rlAssertGrep "/default-1/tests/foo 4" $rlRun_LOG
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartTest "Single '/' test"
        rlRun 'pushd serial-number-root-test'
        rlRun "tmt -vv run --scratch --id $workdir discover -h fmf"
        rlRun -s "yq -er '.[] | \"\\(.name) \\(.\"serial-number\")\"' $workdir/default/plan/discover/tests.yaml"
        rlAssertGrep "/ 1" $rlRun_LOG
        rlRun 'popd'
    rlPhaseEnd

    rlPhaseStartCleanup
        # rlRun "rm -rf $workdir" 0 'Remove tmp directory'
    rlPhaseEnd
rlJournalEnd
