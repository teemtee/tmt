#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "root=/var/tmp/tmt"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Create a couple of runs"
        for id in {001..004}; do
            rlRun "tmt --feeling-safe run --id clean-$id"
            rlAssertExists "$root/clean-$id"
        done
    rlPhaseEnd

    rlPhaseStartTest "Remove last"
        rlRun "tmt clean -v --last"
        rlAssertExists "$root/clean-001"
        rlAssertExists "$root/clean-002"
        rlAssertExists "$root/clean-003"
        rlAssertNotExists "$root/clean-004"
    rlPhaseEnd

    rlPhaseStartTest "Remove selected (full path)"
        rlRun "tmt clean -v --id $root/clean-001"
        rlAssertNotExists "$root/clean-001"
        rlAssertExists "$root/clean-002"
        rlAssertExists "$root/clean-003"
        rlAssertNotExists "$root/clean-004"
    rlPhaseEnd

    rlPhaseStartTest "Remove selected (name)"
        rlRun "tmt clean -v --id clean-002"
        rlAssertNotExists "$root/clean-001"
        rlAssertNotExists "$root/clean-002"
        rlAssertExists "$root/clean-003"
        rlAssertNotExists "$root/clean-004"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
