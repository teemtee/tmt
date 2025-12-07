#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test artifact installation on Fedora"
        # When testing repository-url provider, packages may come from the
        # external repository instead of tmt-artifact-shared
        if [ -n "$TEST_REPO_NAME" ]; then
            # Repository-url provider test: check make comes from the test repo
            rlRun "rpm -q make" 0 "Check that make is installed"
            rlRun -s "dnf info --installed make"
            rlAssertGrep "From repo.*: $TEST_REPO_NAME" $rlRun_LOG

            # Verify the test repository is enabled
            rlRun -s "dnf repo info $TEST_REPO_NAME"
            rlAssertGrep "Status.*: enabled" $rlRun_LOG
        else
            # Standard provider test (koji/file): check make comes from tmt-artifact-shared
            rlRun "rpm -q make" 0 "Check that make is installed"

            # Explicitly check that 'make' comes from our shared artifact repo.
            # This regex matches both "From repo" (dnf4) and "From repository" (dnf5)
            rlRun -s "dnf info --installed make"
            rlAssertGrep "From repo.*: tmt-artifact-shared" $rlRun_LOG

            # Check if the artifact repository is enabled and active in the system
            rlRun -s "dnf repo info tmt-artifact-shared"
            rlAssertGrep "Status.*: enabled" $rlRun_LOG
        fi
    rlPhaseEnd
rlJournalEnd
