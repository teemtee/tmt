#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "rundir=$(mktemp -d)" 0 "Create tmt rundir"
    rlPhaseEnd

    rlPhaseStartTest "Verify tests.yaml without discover_phase is correctly refused"
        rlRun "tests_yaml=$rundir/plans/features/core/discover/tests.yaml"

        # Generate a tests.yaml...
        rlRun "tmt -vv run -i $rundir discover plan -n '^/plans/features/core$'"

        # ... then drop all `discover-phase` keys from discovered test metadata...
        rlRun "yq -y -r 'del(.[].\"discover-phase\")' $tests_yaml > $tests_yaml.edited"
        rlRun "mv $tests_yaml.edited $tests_yaml"

        # ... and run tmt once more to see it report it's not possible to load tests.yaml.
        rlRun -s "tmt -vv run -i $rundir report" 2

        rlAssertGrep "Could not load '$tests_yaml' whose format is not compatible with tmt 1.24 and newer." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $rundir" 0 "Remove tmt rundir"
    rlPhaseEnd
rlJournalEnd
