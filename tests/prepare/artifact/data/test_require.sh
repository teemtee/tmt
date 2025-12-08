#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test artifact installation on Fedora"
        # Verify tmt-artifact-shared repository is enabled
        rlRun -s "dnf repo info tmt-artifact-shared"
        rlAssertGrep "Status.*: enabled" $rlRun_LOG
        rlLog "Repository tmt-artifact-shared is enabled and available"

        # Verify make is installed
        rlRun "rpm -q make" 0 "Check that make is installed"

        # Check that make comes from tmt-artifact-shared
        rlRun -s "dnf info --installed make"
        rlAssertGrep "From repo.*: tmt-artifact-shared" $rlRun_LOG
        rlLog "make comes from expected repository: tmt-artifact-shared"

        # Verify docker-ce repository is enabled
        rlRun -s "dnf repo info docker-ce-stable"
        rlAssertGrep "Status.*: enabled" $rlRun_LOG
        rlLog "Repository docker-ce-stable is enabled and available"

    rlPhaseEnd
rlJournalEnd
