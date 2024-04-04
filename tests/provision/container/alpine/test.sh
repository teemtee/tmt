#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

USER="tester"

rlJournalStart
    rlPhaseStartSetup
        # Directories
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd $tmp"
    rlPhaseEnd

    rlPhaseStartTest "Test vanilla alpine without bash"
        rlRun -s "tmt run --all --id $run --verbose --scratch \
            provision --how container --image docker.io/alpine \
            execute --how tmt --script whoami" 2
        rlAssertGrep "fail: Bash is required on the guest." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test alpine with bash"
        rlRun -s "tmt run -vv --all --id $run --verbose --scratch \
            provision --how container --image localhost/alpine:tmt-tests \
            execute --how tmt --script whoami" 0
        rlAssertGrep "out: root" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp $run" 0 "Remove tmp and run directory"
    rlPhaseEnd
rlJournalEnd
