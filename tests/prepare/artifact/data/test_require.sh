#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test artifact installation on Fedora"
        rlLog "Verifying repositories: ${REPO_LIST:-tmt-artifact-shared}"
        rlLog "Verifying artifacts: ${ARTIFACT_LIST:-make}"

        rlRun "rpm -q make" 0 "Check that make is installed"

        rlRun -s "dnf info --installed make"
        rlAssertGrep "From repo.*: tmt-artifact-shared" $rlRun_LOG
        rlLog "make comes from expected repository: tmt-artifact-shared"

        rlRun -s "dnf repo info tmt-artifact-shared"
        rlAssertGrep "Status.*: enabled" $rlRun_LOG

        if [ -n "$TEST_REPO_NAME" ]; then
            rlRun -s "dnf repo info $TEST_REPO_NAME"
            rlAssertGrep "Status.*: enabled" $rlRun_LOG
            rlLog "Repository $TEST_REPO_NAME is enabled and available"

            rlRun -s "dnf list --available --repo=$TEST_REPO_NAME | head -20"
            rlLog "Available packages from $TEST_REPO_NAME repository"
        fi
    rlPhaseEnd
rlJournalEnd
