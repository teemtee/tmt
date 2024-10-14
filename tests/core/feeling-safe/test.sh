#!/bin/bash

# Include Beaker environment
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "rundir=$(mktemp -d)" 0 "Creating tmp directory"
    rlPhaseEnd

    rlPhaseStartTest "Sanity"
        rlRun -s "tmt                run -i $rundir --scratch provision -h local plan -n /plans/features/core"
        rlAssertNotGrep "User is feeling safe" $rlRun_LOG

        rlRun -s "tmt --feeling-safe run -i $rundir --scratch provision -h local plan -n /plans/features/core"
        rlAssertGrep "User is feeling safe" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $rundir" 0
    rlPhaseEnd
rlJournalEnd
