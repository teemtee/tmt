#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "With $PROVISION_HOW provision method (tty:false)"
        rlRun -s "tmt run -avvvvddd provision -h $PROVISION_HOW"

        rlAssertGrep "stdout: prepare: stdin: False" $rlRun_LOG
        rlAssertGrep "stdout: prepare: stdout: False" $rlRun_LOG
        rlAssertGrep "stdout: prepare: stderr: False" $rlRun_LOG

        rlAssertGrep "stdout: execute: stdin: False" $rlRun_LOG
        rlAssertGrep "stdout: execute: stdout: False" $rlRun_LOG
        rlAssertGrep "stdout: execute: stderr: False" $rlRun_LOG

        rlAssertGrep "stdout: finish: stdin: False" $rlRun_LOG
        rlAssertGrep "stdout: finish: stdout: False" $rlRun_LOG
        rlAssertGrep "stdout: finish: stderr: False" $rlRun_LOG

        rlAssertGrep "stdout: prepare: stdin: 0" $rlRun_LOG
        rlAssertGrep "stdout: prepare: stdout: 0" $rlRun_LOG
        rlAssertGrep "stdout: prepare: stderr: 0" $rlRun_LOG

        rlAssertGrep "stdout: execute: stdin: 0" $rlRun_LOG
        rlAssertGrep "stdout: execute: stdout: 0" $rlRun_LOG
        rlAssertGrep "stdout: execute: stderr: 0" $rlRun_LOG

        rlAssertGrep "stdout: finish: stdin: 0" $rlRun_LOG
        rlAssertGrep "stdout: finish: stdout: 0" $rlRun_LOG
        rlAssertGrep "stdout: finish: stderr: 0" $rlRun_LOG

        # test for #2429, not related to tty
        rlRun -s "tmt run --last report -vvv"
        rlAssertNotGrep "Connection to.*closed" $rlRun_LOG
        rlAssertNotGrep "Shared connection to.*closed" $rlRun_LOG
    rlPhaseEnd

    # NOTE: Our local provisioner cannot execute commands with a pty allocated
    if [ "$PROVISION_HOW" != "local" ]; then
            rlPhaseStartTest "With $PROVISION_HOW provision method (tty:true)"
                rlRun -s "NO_COLOR=1 ../ptty-wrapper tmt -c tty=true run -avvvvddd provision -h $PROVISION_HOW" 1

                rlAssertGrep "stdout: prepare: stdin: False" $rlRun_LOG
                rlAssertGrep "stdout: prepare: stdout: False" $rlRun_LOG
                rlAssertGrep "stdout: prepare: stderr: False" $rlRun_LOG

                rlAssertGrep "stdout: execute: stdin: True" $rlRun_LOG
                rlAssertGrep "stdout: execute: stdout: True" $rlRun_LOG
                rlAssertGrep "stdout: execute: stderr: True" $rlRun_LOG

                rlAssertGrep "stdout: finish: stdin: False" $rlRun_LOG
                rlAssertGrep "stdout: finish: stdout: False" $rlRun_LOG
                rlAssertGrep "stdout: finish: stderr: False" $rlRun_LOG

                rlAssertGrep "stdout: prepare: stdin: 0" $rlRun_LOG
                rlAssertGrep "stdout: prepare: stdout: 0" $rlRun_LOG
                rlAssertGrep "stdout: prepare: stderr: 0" $rlRun_LOG

                rlAssertGrep "stdout: execute: stdin: 1" $rlRun_LOG
                rlAssertGrep "stdout: execute: stdout: 1" $rlRun_LOG
                rlAssertGrep "stdout: execute: stderr: 1" $rlRun_LOG

                rlAssertGrep "stdout: finish: stdin: 0" $rlRun_LOG
                rlAssertGrep "stdout: finish: stdout: 0" $rlRun_LOG
                rlAssertGrep "stdout: finish: stderr: 0" $rlRun_LOG
            rlPhaseEnd
    fi

    rlPhaseStartTest "With $PROVISION_HOW provision method, interactive tests"
        rlRun -s "NO_COLOR=1 ../ptty-wrapper tmt run -avvvvddd provision -h $PROVISION_HOW execute -h tmt --interactive" 1

        rlAssertGrep "stdout: prepare: stdin: False" $rlRun_LOG
        rlAssertGrep "stdout: prepare: stdout: False" $rlRun_LOG
        rlAssertGrep "stdout: prepare: stderr: False" $rlRun_LOG

        rlAssertGrep "execute: stdin: True" $rlRun_LOG
        rlAssertGrep "execute: stdout: True" $rlRun_LOG
        rlAssertGrep "execute: stderr: True" $rlRun_LOG

        rlAssertGrep "stdout: finish: stdin: False" $rlRun_LOG
        rlAssertGrep "stdout: finish: stdout: False" $rlRun_LOG
        rlAssertGrep "stdout: finish: stderr: False" $rlRun_LOG

        rlAssertGrep "stdout: prepare: stdin: 0" $rlRun_LOG
        rlAssertGrep "stdout: prepare: stdout: 0" $rlRun_LOG
        rlAssertGrep "stdout: prepare: stderr: 0" $rlRun_LOG

        rlAssertGrep "execute: stdin: 1" $rlRun_LOG
        rlAssertGrep "execute: stdout: 1" $rlRun_LOG
        rlAssertGrep "execute: stderr: 1" $rlRun_LOG

        rlAssertGrep "stdout: finish: stdin: 0" $rlRun_LOG
        rlAssertGrep "stdout: finish: stdout: 0" $rlRun_LOG
        rlAssertGrep "stdout: finish: stderr: 0" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
