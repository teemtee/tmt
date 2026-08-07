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
        rlRun -s "TMT_FEELING_SAFE= tmt $options" 2
        rlAssertNotGrep "User is feeling safe" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Feeling Safe"
        # Command line option
        rlRun -s "tmt --feeling-safe=all $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --feeling-safe=1 $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --feeling-safe=provision/local $options"
        rlAssertGrep "User is feeling safe: 'local' provisioning plugin allowed" $rlRun_LOG

        rlRun -s "tmt --feeling-safe=provision/local --feeling-safe=all $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --feeling-safe=provision/local --feeling-safe=1 $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --feeling-safe=none $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --feeling-safe=0 $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --feeling-safe=provision/local --feeling-safe=all --feeling-safe=none $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --feeling-safe=provision/local --feeling-safe=all --feeling-safe=0 $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        # Environment variable
        rlRun -s "TMT_FEELING_SAFE=all tmt $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_FEELING_SAFE=1 tmt $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_FEELING_SAFE=provision/local tmt $options"
        rlAssertGrep "User is feeling safe: 'local' provisioning plugin allowed" $rlRun_LOG

        rlRun -s "TMT_FEELING_SAFE='provision/local all' tmt $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_FEELING_SAFE='provision/local 1' tmt $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_FEELING_SAFE=none tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_FEELING_SAFE=0 tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_FEELING_SAFE='provision/local all none' tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_FEELING_SAFE='provision/local all 0' tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $rundir" 0
    rlPhaseEnd
rlJournalEnd
