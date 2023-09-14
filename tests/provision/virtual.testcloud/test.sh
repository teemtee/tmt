#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

PROVISION_METHODS=${PROVISION_METHODS:-virtual.testcloud}

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
            rlAssertGrep "memory: 2048 megabyte" "$run/log.txt"
            rlAssertGrep "disk: 10 gigabyte" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: memory: == 2048 megabyte" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: disk.size: == 10 gigabyte" "$run/log.txt"
            rlAssertGrep "memory: set to '2048 megabyte' because of 'memory: == 2048 megabyte'" "$run/log.txt"
            rlAssertGrep "disk\\[0\\].size: set to '10 gigabyte' because of 'disk.size: == 10 gigabyte'" "$run/log.txt"
            rlAssertGrep "final domain memory: 2048000" "$run/log.txt"
            rlAssertGrep "final domain disk size: 10" "$run/log.txt"
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
            rlAssertGrep "memory: 2049 megabyte" "$run/log.txt"
            rlAssertGrep "disk: 11 gigabyte" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: memory: == 2049 megabyte" "$run/log.txt"
            rlAssertGrep "effective hardware: variant #1: disk.size: == 11 gigabyte" "$run/log.txt"
            rlAssertGrep "memory: set to '2049 megabyte' because of 'memory: == 2049 megabyte'" "$run/log.txt"
            rlAssertGrep "disk\\[0\\].size: set to '11 gigabyte' because of 'disk.size: == 11 gigabyte'" "$run/log.txt"
            rlAssertGrep "final domain memory: 2049000" "$run/log.txt"
            rlAssertGrep "final domain disk size: 11" "$run/log.txt"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Boots fedora-coreos image"
      if ! rlRun "tmt run -i $run --scratch \
          plans --default finish login -c echo \
          provision -h virtual.testcloud --image fedora-coreos"; then
         rlRun "cat $run/log.txt" 0 "Dump log.txt"
      fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
