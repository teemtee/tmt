#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

USER="tester"

rlJournalStart
    rlPhaseStartSetup
        # Try several times to build the container
        # https://github.com/teemtee/tmt/issues/2063
        build="make -C ../../../../ images-tests/tmt/tests/alpine\:latest images-tests/tmt/tests/alpine/upstream\:latest"
        rlRun "rlWaitForCmd '$build' -m 5 -d 5 -t 3600" || rlDie "Unable to prepare the images"

        # Directories
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd $tmp"
    rlPhaseEnd

    rlPhaseStartTest "Test vanilla alpine without bash"
        rlRun -s "tmt run --all --id $run --verbose --scratch \
            provision --how container --image localhost/tmt/tests/container/alpine/upstream:latest \
            execute --how tmt --script whoami" 2
        rlAssertGrep "fail: /bin/bash is required on the guest." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test alpine with bash"
        rlRun -s "tmt run -vv --all --id $run --verbose --scratch \
            provision --how container --image localhost/tmt/tests/container/alpine:latest \
            execute --how tmt --script whoami" 0
        rlAssertGrep "out: root" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp $run" 0 "Remove tmp and run directory"
    rlPhaseEnd
rlJournalEnd
