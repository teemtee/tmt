#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init"
        rlRun "tmt plan create -t mini plan1"
        rlRun "tmprun=\$(mktemp -d)" 0 "Create a temporary directory for runs"

        rlRun "run1=$tmprun/1"
        rlRun "tmt run -i $run1 discover"

        rlRun "run2=$tmprun/2"
        rlRun "tmt run -i $run2 discover"
    rlPhaseEnd

    rlPhaseStartTest "Dry mode"
        rlRun -s "tmt clean runs --dry -v --workdir-root $tmprun"
        rlAssertGrep "Would remove workdir '$run1'" "$rlRun_LOG"
        rlAssertGrep "Would remove workdir '$run2'" "$rlRun_LOG"
        rlRun -s "tmt status --workdir-root $tmprun -vv"
        rlAssertGrep "(done\s+){1}(todo\s+){6}$run1\s+/plan1" "$rlRun_LOG" -E
        rlAssertGrep "(done\s+){1}(todo\s+){6}$run2\s+/plan1" "$rlRun_LOG" -E
    rlPhaseEnd

    rlPhaseStartTest "Specify ID"
        rlRun -s "tmt clean runs -v -i $run1"
        rlAssertGrep "Removing workdir '$run1'" "$rlRun_LOG"
        rlRun -s "tmt status --workdir-root $tmprun -vv"
        rlAssertNotGrep "(done\s+){1}(todo\s+){6}$run1\s+/plan1" "$rlRun_LOG" -E
        rlAssertGrep "(done\s+){1}(todo\s+){6}$run2\s+/plan1" "$rlRun_LOG" -E

        rlRun -s "tmt clean runs -v -l --workdir-root $tmprun"
        rlAssertGrep "Removing workdir '$run2'" "$rlRun_LOG"
        rlRun -s "tmt status --workdir-root $tmprun -vv"
        rlAssertNotGrep "(done\s+){1}(todo\s+){6}$run2\s+/plan1" "$rlRun_LOG" -E

        rlRun "wc -l '$rlRun_LOG' | tee lines" 0 "Get the number of lines"
        rlLog "The status should only contain the heading"
        rlAssertGrep "1" "lines"
    rlPhaseEnd

    rlPhaseStartTest "Keep N"
        for i in $(seq 1 10); do
            rlRun "tmt run -i $tmprun/$i discover"
        done
        rlRun "tmt clean runs -v --keep 10 --workdir-root $tmprun"
        rlRun -s "tmt status --workdir-root $tmprun -vv"
        rlLog "The runs should remain intact"
        for i in $(seq 1 10); do
            rlAssertGrep "$tmprun/$i\s+/plan1" "$rlRun_LOG" -E
        done

        rlRun "tmt clean runs -v --keep 2 --workdir-root $tmprun"
        rlRun -s "tmt status --workdir-root $tmprun -vv"
        rlAssertGrep "$tmprun/9" "$rlRun_LOG"
        rlAssertGrep "$tmprun/10" "$rlRun_LOG"

        for i in $(seq 1 8); do
            rlAssertNotGrep "$tmprun/$i\s+/plan1" "$rlRun_LOG" -E
        done

        rlRun "tmt clean runs -v --keep 1 --workdir-root $tmprun"
        rlRun -s "tmt status --workdir-root $tmprun -vv"
        rlAssertNotGrep "$tmprun/9" "$rlRun_LOG"
        rlAssertGrep "$tmprun/10" "$rlRun_LOG"

        rlRun "tmt clean runs -v --keep 0 --workdir-root $tmprun"
        rlRun -s "tmt status --workdir-root $tmprun -vv"
        rlAssertNotGrep "$tmprun/10" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Remove everything"
        for i in $(seq 1 10); do
            rlRun "tmt run -i $tmprun/$i discover"
        done
        rlRun "tmt clean runs -v --workdir-root $tmprun"
        rlRun -s "tmt status -vv --workdir-root $tmprun"
        rlRun "wc -l '$rlRun_LOG' | tee lines" 0 "Get the number of lines"
        rlLog "The status should only contain the heading"
        rlAssertGrep "1" "lines"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $tmprun" 0 "Remove a temporary directory for runs"
    rlPhaseEnd
rlJournalEnd
