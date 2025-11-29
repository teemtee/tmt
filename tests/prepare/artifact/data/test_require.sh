#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test artifact installation on Fedora"
        rlRun "rpm -q make" 0 "Check that make is installed"
        rlRun -s "dnf info --installed make"
        # Check that the package was installed from our specific artifact repository
        # Matches "From repo : tmt-artifact-shared" or "From repository : tmt-artifact-shared"
        rlAssertGrep "From repo.*: tmt-artifact-shared" $rlRun_LOG

        # Check if the artifact repository is enabled and active in the system
        rlRun "dnf repolist --enabled | grep -q '^tmt-artifact-shared'" 0 "Check if artifact repo is active"
    rlPhaseEnd
rlJournalEnd
