#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "tmt init"
        rlRun "tmt test create -t shell tests/test"
        rlRun "tmt plans create -t mini plans/test-plan"
        rlRun "tmt run --until report provision -h local"
        rlRun "cd .. && tmt run -vvvdddr --last --since report"
    rlPhaseEnd

    rlPhaseStartTest "Test create runs in non-default workdir-root"
        rlRun "popd"
        rlRun "pushd data"
        rlRun "test_root=\$(mktemp -d)"
        for id in {001..003}; do
            rlRun "tmt --feeling-safe run --workdir-root $test_root --id run-$id"
            rlAssertExists "$test_root/run-$id"
        done
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
        rlRun "rm -r $test_root" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
