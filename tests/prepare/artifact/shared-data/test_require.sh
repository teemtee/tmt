#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

# Parameters:
# $1 - REPO_LIST: Comma-separated list of repositories to verify (e.g., "tmt-artifact-shared" or "test-fedora,tmt-artifact-shared")
# $2 - ARTIFACT_LIST: Comma-separated list of artifacts/packages to verify (e.g., "make" or "make,vim")

REPO_LIST="${1:-tmt-artifact-shared}"
ARTIFACT_LIST="${2:-make}"

rlJournalStart
    rlPhaseStartTest "Test artifact installation on Fedora"
        rlLog "Verifying repositories: $REPO_LIST"
        rlLog "Verifying artifacts: $ARTIFACT_LIST"

        # Verify each artifact is installed
        IFS=',' read -ra ARTIFACTS <<< "$ARTIFACT_LIST"
        for artifact in "${ARTIFACTS[@]}"; do
            artifact=$(echo "$artifact" | xargs)  # trim whitespace
            rlRun "rpm -q $artifact" 0 "Check that $artifact is installed"
        done

        # Verify each repository is enabled
        IFS=',' read -ra REPOS <<< "$REPO_LIST"
        for repo in "${REPOS[@]}"; do
            repo=$(echo "$repo" | xargs)  # trim whitespace
            rlRun -s "dnf repo info $repo"
            rlAssertGrep "Status.*: enabled" $rlRun_LOG "Verify $repo repository is enabled"
        done

        # For the first artifact, verify it comes from one of the expected repositories
        first_artifact="${ARTIFACTS[0]}"
        rlRun -s "dnf info --installed $first_artifact"

        # Check that the artifact comes from one of the expected repos
        # This regex matches both "From repo" (dnf4) and "From repository" (dnf5)
        repo_found=false
        for repo in "${REPOS[@]}"; do
            repo=$(echo "$repo" | xargs)  # trim whitespace
            if grep -q "From repo.*: $repo" $rlRun_LOG 2>/dev/null; then
                rlLog "$first_artifact comes from expected repository: $repo"
                repo_found=true
                break
            fi
        done

        if [ "$repo_found" = false ]; then
            rlFail "$first_artifact does not come from any expected repository: $REPO_LIST"
        fi
    rlPhaseEnd
rlJournalEnd
