#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test artifact installation on Fedora"
        rlRun "rpm -q make" 0 "Check that make is installed"

        # Explicitly check that 'make' comes from our shared artifact repo.
        # This regex matches both "From repo" (dnf4) and "From repository" (dnf5)
        rlRun -s "dnf info --installed make"
        rlAssertGrep "From repo.*: tmt-artifact-shared" $rlRun_LOG

        # Check if the artifact repository is enabled and active in the system
        rlRun -s "dnf repo info tmt-artifact-shared"
        rlAssertGrep "Status.*: enabled" $rlRun_LOG
    rlPhaseEnd
rlJournalEnd
