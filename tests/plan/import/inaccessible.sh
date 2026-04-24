#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Unimportable plan should not raise errors when disabled"
        rlRun -s "tmt -ddd plan ls /plans/inaccessible/disabled$" 2 "Error out when trying to import internal URL"
        rlAssertGrep "Plan '/plans/inaccessible/disabled' importing" $rlRun_LOG
        rlAssertGrep "Failed to import remote plan from '/plans/inaccessible/disabled'" $rlRun_LOG

        rlRun -s "tmt -ddd plan ls /plans/inaccessible/disabled$ --enabled" 0 "Skip disabled plan with --enabled flag"
        rlAssertNotGrep "Plan '/plans/inaccessible/disabled' importing" $rlRun_LOG
        rlAssertNotGrep "Failed to import remote plan from '/plans/inaccessible/disabled'" $rlRun_LOG

        rlRun -s "tmt -ddd plan show /plans/inaccessible/disabled$" 2 "Error out when showing"
        rlAssertGrep "Plan '/plans/inaccessible/disabled' importing" $rlRun_LOG
        rlAssertGrep "Failed to import remote plan from '/plans/inaccessible/disabled'" $rlRun_LOG

        rlRun -s "tmt -ddd plan show /plans/inaccessible/disabled$ --shallow" 0 "Show dummy plan"
        rlAssertNotGrep "Plan '/plans/inaccessible/disabled' importing" $rlRun_LOG
        rlAssertNotGrep "Failed to import remote plan from '/plans/inaccessible/disabled'" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
