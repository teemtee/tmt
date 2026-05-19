#!/bin/bash
# Outer beakerlib test for the artifact-plugin DNF behaviour suite.
#
# Builds all RPM repos from spec files in data/, then iterates over each
# inner plan defined in data/ and runs it in a container that matches the
# current distro.
#
# Run on Fedora  → inner container is fedora:<release>
# Run on CentOS  → inner container is quay.io/centos/centos:stream<release>

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup "Prepare test environment"
        PROVISION_HOW=${PROVISION_HOW:-container}
        rlRun "testdir=$(mktemp -d)" 0 "Create test directory"
        rlRun "cp -a data $testdir" 0 "Copy test data"
        rlRun "pushd $testdir/data" 0 "Enter test data directory"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"

        if false; then
            release=$(rlGetDistroRelease)
            image="fedora:${release}"
        elif true; then
            release=$(rlGetDistroRelease)
            image="quay.io/centos/centos:stream8"
        else
            rlDie "Unsupported distro: test requires Fedora or CentOS"
        fi
        rlLog "Inner container image: $image"
    rlPhaseEnd

    rlPhaseStartSetup "Build RPM repos"
        rlRun "./build-repos.sh" 0 "Build RPM repos from spec files"
    rlPhaseEnd

    for plan in $(tmt plans ls); do
        rlPhaseStartTest "$plan"
            rlRun "tmt run -i $run --scratch -vvv --all \
                plan --name $plan \
                provision -h $PROVISION_HOW --image $image" \
                0 "$plan"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run $testdir" 0 "Remove run and test directories"
    rlPhaseEnd
rlJournalEnd
