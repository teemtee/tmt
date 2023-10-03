#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Show plan"
        # Without context
        rlRun -s "tmt plan show" 0 "Plan should not be enabled"
        rlAssertGrep "enabled false" $rlRun_LOG

        # Context is the same as the plan
        rlRun -s "tmt -c foo=bar plan show" 0 "Plan should be enabled"
        rlAssertGrep "enabled true" $rlRun_LOG

        # Context is the same as the plan but with different case
        rlRun -s "tmt -c foo=BaR plan show" 0 "Plan should be enabled"
        rlAssertGrep "enabled true" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
