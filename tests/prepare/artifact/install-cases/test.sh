#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1
. ../lib/common.sh || exit 1

rlJournalStart
    rlPhaseStartSetup "Prepare test environment"
        PROVISION_HOW=${PROVISION_HOW:-container}
        rlRun "testdir=$(mktemp -d)" 0 "Create test directory"
        rlRun "cp -a data $testdir" 0 "Copy test data"
        rlRun "pushd $testdir/data" 0 "Enter test directory"
        rlRun "run=$(mktemp -d)" 0 "Create run directory"
    rlPhaseEnd

    rlPhaseStartSetup "Build RPM repos"
        for repo_dir in rpms/*; do
            rlRun "pushd $repo_dir"
            rlRun "rpmbuild --define='_topdir build' -bb *.spec" 0 "Build rpms"
            rlRun "cp build/RPMS/*/* ./" 0 "Move rpms next to spec file"
            rlRun "popd"
        done
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run $testdir" 0 "Remove temporary files directories"
    rlPhaseEnd
rlJournalEnd
