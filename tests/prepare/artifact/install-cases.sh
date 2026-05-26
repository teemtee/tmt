#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup "Prepare test environment"
        rlRun "pushd install-cases" 0 "Enter test directory"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"

        setup_distro_environment
        build_rpms
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove temporary files directories"
    rlPhaseEnd
rlJournalEnd
