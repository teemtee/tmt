#!/bin/bash
# Outer beakerlib test for the nvr-debug suite.
#
# Flow:
#   Setup   - prepare run directories (one per TC)
#   TC 1.1  - priority=1 repo (v1.0) beats priority=100 repo (v2.0)
#   TC 1.2  - same priority repos: highest NVR (v2.0) wins
#   Cleanup - remove run directories
#
# Each tmt run:
#   1. Runs build-repos.sh via the plan's shell prepare step (order=40)
#      to build two dummy RPMs and create two local repos inside the
#      container at /tmp/nvr-test/repo-high (v1.0) and repo-low (v2.0).
#   2. Inserts a repository-file artifact step (order=50) that copies
#      the appropriate .repo files (from this directory) into the
#      container's /etc/yum.repos.d/.
#   3. The install step (order=70) satisfies the test's
#      'require: dummy-nvr-test' by running DNF, which picks the
#      package according to the configured priorities.

. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "pushd data"

        rlRun "run1=$(mktemp -d)" 0 "Create run directory for TC 1.1"
        rlRun "run2=$(mktemp -d)" 0 "Create run directory for TC 1.2"

        setup_distro_environment
    rlPhaseEnd

    rlPhaseStartTest "TC 1.1 - Repository priority overrides package version"
        rlLog "repo-high (priority=1)   provides dummy-nvr-test-1.0"
        rlLog "repo-low  (priority=100) provides dummy-nvr-test-2.0"
        rlLog "Expected: DNF5 installs v1.0 because priority=1 wins"

        # --insert adds the artifact step alongside the shell step already
        # in the plan (order=40), rather than replacing it.
        # The artifact step copies tc11-high.repo and tc11-low.repo into
        # /etc/yum.repos.d/ inside the container before the install step runs.
        rlRun "tmt run -i $run1 --scratch -vvv --all \
            plan -n /tc11 \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --insert --how artifact \
                --provide repository-file:$(pwd)/tc11-high.repo \
                --provide repository-file:$(pwd)/tc11-low.repo" \
            0 "TC 1.1: high-priority repo (v1.0) beats low-priority repo (v2.0)"
    rlPhaseEnd

    rlPhaseStartTest "TC 1.2 - Same priority falls back to NVR comparison"
        rlLog "repo A (priority=50) provides dummy-nvr-test-1.0"
        rlLog "repo B (priority=50) provides dummy-nvr-test-2.0"
        rlLog "Expected: DNF5 installs v2.0 because it has the higher NVR"

        rlRun "tmt run -i $run2 --scratch -vvv --all \
            plan -n /tc12 \
            provision -h $PROVISION_HOW --image $TEST_IMAGE_PREFIX/$image_name \
            prepare --insert --how artifact \
                --provide repository-file:$(pwd)/tc12-a.repo \
                --provide repository-file:$(pwd)/tc12-b.repo" \
            0 "TC 1.2: same-priority repos, highest NVR (v2.0) wins"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run1 $run2" 0 "Remove run directories"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
