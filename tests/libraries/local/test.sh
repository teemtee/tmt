#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup "Prepare library"
        rlRun "libdir=\$(mktemp -d)" 0 "Create libdir directory"
        rlRun "pushd $libdir"
        rlWaitForCmd "git clone https://github.com/beakerlib/example" -m 5 -d 10 -t 300 || rlDie "Unable to clone beakerlib/example repository"
        rlRun "sed -i 's/Creating file/Create fyle/' example/file/lib.sh"
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartSetup "Prepare test (local filesystem)"
        rlRun "testdir_local=\$(mktemp -d)" 0 "Create testdir directory"
        rlRun "cp -a data $testdir_local"
        rlRun "sed -i 's|PATH|${libdir}/example|' $testdir_local/data/main.fmf"
    rlPhaseEnd

    rlPhaseStartTest "Test library in local filesystem"
        rlRun "pushd $testdir_local/data"
        rlRun "set -o pipefail"
        rlRun "tmt run -ar discover -vvvddd report -vvv 2>&1 >/dev/null | tee output"
        rlAssertGrep "Copy local library.*example" "output"
        rlAssertGrep "Create fyle 'fooo'" "output"
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartSetup "Prepare test (relative to tmt tree)"
        rlRun "testdir_tree=\$(mktemp -d)" 0 "Create testdir directory"
        rlRun "cp -a data $testdir_tree"
        # Assuming libdir/example does not have a top-level main.fmf or test.sh that would override ours
        rlRun "cp -a $libdir/example/* $testdir_tree/data" 0 "Copy library to tmt tree"
        rlRun "sed -i 's|path: PATH|nick: example|' $testdir_tree/data/main.fmf" 0 "Use nick instead of path"
        rlRun "mv  $testdir_tree/data  $testdir_tree/example" 0 "Rename tree base to match the library's"
    rlPhaseEnd

    rlPhaseStartTest "Test library relative to tmt tree"
        rlRun "pushd $testdir_tree/example"
        rlRun "set -o pipefail"
        rlRun "tmt run -ar discover -vvvddd report -vvv 2>&1 >/dev/null | tee output"
        rlAssertGrep "Copy local library.*example" "output"
        rlAssertGrep "Create fyle 'fooo'" "output"
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $libdir $testdir_local $testdir_tree" 0 "Remove temporary directories"
    rlPhaseEnd
rlJournalEnd
