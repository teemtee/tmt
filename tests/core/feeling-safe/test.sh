#!/bin/bash

# Include Beaker environment
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "rundir=$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "options='run -i $rundir --scratch provision -h local plan -n /plans/features/core'"
        rlRun "unset TMT_FEELING_SAFE"
    rlPhaseEnd

    rlPhaseStartTest "Feeling Paranoid"
        # Command line option
        rlRun -s "tmt $options" 2
        rlAssertNotGrep "User is feeling safe" $rlRun_LOG

        # Environment variable
        rlRun -s "TMT_FEELING_SAFE=0 tmt $options" 2
        rlAssertNotGrep "User is feeling safe" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Feeling Safe"
        # Command line option
        rlRun -s "tmt --feeling-safe $options"
        rlAssertGrep "User is feeling safe" $rlRun_LOG

        # Environment variable
        rlRun -s "TMT_FEELING_SAFE=1 tmt $options"
        rlAssertGrep "User is feeling safe" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $rundir" 0
    rlPhaseEnd
rlJournalEnd
