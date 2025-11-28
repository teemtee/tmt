#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test artifact installation on Fedora"
        # Set defaults if not provided
        REPO_LIST="${REPO_LIST:-tmt-artifact-shared}"
        ARTIFACT_LIST="${ARTIFACT_LIST:-make}"

        rlLog "Verifying repositories: $REPO_LIST"
        rlLog "Verifying artifacts: $ARTIFACT_LIST"

        # Verify all repositories in REPO_LIST are enabled
        IFS=',' read -ra REPOS <<< "$REPO_LIST"
        for repo in "${REPOS[@]}"; do
            rlRun -s "dnf repo info $repo"
            rlAssertGrep "Status.*: enabled" $rlRun_LOG
            rlLog "Repository $repo is enabled and available"
        done

        # Verify all artifacts in ARTIFACT_LIST are installed
        IFS=',' read -ra ARTIFACTS <<< "$ARTIFACT_LIST"
        for artifact in "${ARTIFACTS[@]}"; do
            rlRun "rpm -q $artifact" 0 "Check that $artifact is installed"
        done

        # Check that make comes from tmt-artifact-shared
        rlRun -s "dnf info --installed make"
        rlAssertGrep "From repo.*: tmt-artifact-shared" $rlRun_LOG
        rlLog "make comes from expected repository: tmt-artifact-shared"

        # If TEST_REPO_NAME is set, list available packages from it
        if [ -n "$TEST_REPO_NAME" ]; then
            rlRun -s "dnf list --available --repo=$TEST_REPO_NAME | head -20"
            rlLog "Available packages from $TEST_REPO_NAME repository"
        fi
    rlPhaseEnd
rlJournalEnd
