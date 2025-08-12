#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
    rlPhaseEnd

    rlPhaseStartTest "Check base memory is defaulted to hardware memory"
        if ! rlRun "tmt run -i $run -vv --all plan --name /plans/hardware-only" ; then
            rlRun "cat $run/log.txt" 0 "Dump log.txt"
        else
            rlAssertGrep "memory: 8000 MB" "$run/log.txt"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Check base memory overrides hardware memory"
        if ! rlRun "tmt run -i $run -vv --all plan --name /plans/override" ; then
            rlRun "cat $run/log.txt" 0 "Dump log.txt"
        else
            rlAssertGrep "memory: 4000 MB" "$run/log.txt"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Check base memory is defaulted to 2048 MB"
        if ! rlRun "tmt run -i $run -vv --all plan --name /plans/default" ; then
            rlRun "cat $run/log.txt" 0 "Dump log.txt"
        else
            rlAssertGrep "memory: 2048 MB" "$run/log.txt"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
