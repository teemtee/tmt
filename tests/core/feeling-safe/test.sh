#!/bin/bash

# Include Beaker environment
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "rundir=$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "options='run -i $rundir --scratch provision -h local plan -n /plans/features/core'"
        rlRun "unset TMT_FEELING_SAFE"
        rlRun "unset TMT_ALLOW_UNSAFE_BEHAVIOR"
    rlPhaseEnd

    rlPhaseStartTest "Feeling Paranoid"
        # Command line option
        rlRun -s "tmt $options" 2
        rlAssertNotGrep "User is feeling safe" $rlRun_LOG

        # Environment variable
        rlRun -s "TMT_FEELING_SAFE= tmt $options" 2
        rlAssertNotGrep "User is feeling safe" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR= tmt $options" 2
        rlAssertNotGrep "User is feeling safe" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Feeling Safe"
        # Command line option
        rlRun -s "tmt --allow-unsafe-behavior=all $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=1 $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=provision/local $options"
        rlAssertGrep "User is feeling safe: 'local' provisioning plugin allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=provision/local --allow-unsafe-behavior=all $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=provision/local --allow-unsafe-behavior=1 $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=provision/local --feeling-safe $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=none $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=0 $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=provision/local --allow-unsafe-behavior=all --allow-unsafe-behavior=none $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=provision/local --allow-unsafe-behavior=all --allow-unsafe-behavior=0 $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=provision/local --feeling-safe --allow-unsafe-behavior=none $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "tmt --allow-unsafe-behavior=provision/local --feeling-safe --allow-unsafe-behavior=0 $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        # Environment variable
        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR=all tmt $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR=1 tmt $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR=provision/local tmt $options"
        rlAssertGrep "User is feeling safe: 'local' provisioning plugin allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR='provision/local all' tmt $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR='provision/local 1' tmt $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR='provision/local' TMT_FEELING_SAFE=1 tmt $options"
        rlAssertGrep "User is feeling safe: all unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR=none tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR=0 tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR='provision/local all none' tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR='provision/local all 0' tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR='provision/local none' TMT_FEELING_SAFE=1 tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR='provision/local 0' TMT_FEELING_SAFE=1 tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR='provision/local all' TMT_FEELING_SAFE=0 tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG

        rlRun -s "TMT_ALLOW_UNSAFE_BEHAVIOR='provision/local 1' TMT_FEELING_SAFE=0 tmt $options" 2
        rlAssertGrep "User is not feeling safe: no unsafe behavior allowed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $rundir" 0
    rlPhaseEnd
rlJournalEnd
