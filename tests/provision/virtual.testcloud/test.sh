#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

SRC_PLAN="$(pwd)/data/plan.fmf"

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init"
    rlPhaseEnd

    rlPhaseStartTest "All options used in plan"
        rlRun "cp $SRC_PLAN ."

        if ! rlRun "tmt run -i $run --scratch"; then
            rlRun "cat $run/log.txt" 0 "Dump log.txt"
        else
            rlAssertGrep "memory: 2048 MB" "$run/log.txt"
            rlAssertGrep "disk: 10 GB" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: memory: == 2048 MB" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: disk\\[0\\].size: == 10 GB" "$run/log.txt"
            rlAssertGrep "memory: set to '2048 MB' because of 'memory: == 2048 MB'" "$run/log.txt"
            rlAssertGrep "disk\\[0\\].size: set to '10 GB' because of 'disk\\[0\\].size: == 10 GB'" "$run/log.txt"
            rlAssertGrep "final domain memory: 2048000" "$run/log.txt"
            rlAssertGrep "final domain root disk size: 10" "$run/log.txt"
        fi
    rlPhaseEnd

    rlPhaseStartTest "All options used in plan from cmdline"
        rlRun "cp $SRC_PLAN ."

        if ! rlRun "tmt run -i $run --scratch --all \
                            provision -h virtual.testcloud \
                                      --image fedora \
                                      --disk 11 \
                                      --memory 2049 \
                                      --connection system" ; then
            rlRun "cat $run/log.txt" 0 "Dump log.txt"
        else
            rlAssertGrep "memory: 2049 MB" "$run/log.txt"
            rlAssertGrep "disk: 11 GB" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: memory: == 2049 MB" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: disk\\[0\\].size: == 11 GB" "$run/log.txt"
            rlAssertGrep "memory: set to '2049 MB' because of 'memory: == 2049 MB'" "$run/log.txt"
            rlAssertGrep "disk\\[0\\].size: set to '11 GB' because of 'disk\\[0\\].size: == 11 GB'" "$run/log.txt"
            rlAssertGrep "final domain memory: 2049000" "$run/log.txt"
            rlAssertGrep "final domain root disk size: 11" "$run/log.txt"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Boots fedora-coreos image"
      if ! rlRun "tmt run -i $run --scratch \
          plans --default finish login -c echo \
          provision -h virtual.testcloud --image fedora-coreos"; then
         rlRun "cat $run/log.txt" 0 "Dump log.txt"
      fi
    rlPhaseEnd

    rlPhaseStartTest "Provision a guest with multiple disks"
        rlRun "cp $SRC_PLAN ."

        if ! rlRun "tmt run -i $run --scratch --all \
                        provision -h virtual.testcloud \
                                  --hardware disk[1].size=22GB \
                                  --hardware disk[2].size=33GB \
                                  --connection system"; then
            rlRun "cat $run/log.txt" 0 "Dump log.txt"
        else
            rlAssertGrep "effective hardware: variant #1: disk\\[0\\].size: == 10 GB" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: disk\\[1\\].size: == 22 GB" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: disk\\[2\\].size: == 33 GB" "$run/log.txt"

            rlAssertGrep "disk\\[0\\].size: set to '10 GB' because of 'disk\\[0\\].size: == 10 GB'" "$run/log.txt"
            rlAssertGrep "disk\\[1\\].size: set to '22 GB' because of 'disk\\[1\\].size: == 22 GB'" "$run/log.txt"
            rlAssertGrep "disk\\[2\\].size: set to '33 GB' because of 'disk\\[2\\].size: == 33 GB'" "$run/log.txt"

            rlAssertGrep "final domain root disk size: 10" "$run/log.txt"
            rlAssertGrep "final domain disk #0 size: 10" "$run/log.txt"
            rlAssertGrep "final domain disk #1 size: 22" "$run/log.txt"
            rlAssertGrep "final domain disk #2 size: 33" "$run/log.txt"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
