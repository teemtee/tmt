#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

set -o pipefail

rlJournalStart
    rlPhaseStartSetup "Prepare library and test"
        rlRun "libdir=\$(mktemp -d)"
        rlRun "cp -r lib/* $libdir"
        rlRun "tmt init $libdir"

        rlRun "testdir=\$(mktemp -d)"
        rlRun "cp -r data/* $testdir"
        rlRun "pushd $testdir"
        rlRun "tmt init"
        rlRun "git init"
        rlRun "git config --local user.email me@localhost.localdomain"
        rlRun "git config --local user.name m e"
        rlRun "git add -A"
        rlRun "git commit -m initial"
        rlRun "sed 's|PATH|$libdir|' -i main.fmf"
    rlPhaseEnd

    rlPhaseStartTest "Test layered library fmf"
        rlRun -s "tmt run --rm -a -vvv -ddd provision -h local"
        rlAssertGrep "1 tests passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $libdir $testdir" 0 "Remove temporary directories"
    rlPhaseEnd
rlJournalEnd
