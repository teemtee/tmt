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
        rlRun -s "tmt run --until provision provision -h container"
        rlRun "runid=\$(head -n 1 '$rlRun_LOG')" 0 "Get the run ID"
    rlPhaseEnd

    rlPhaseStartTest "Dry mode"
        rlRun -s "tmt status -vv"
        rlAssertGrep "(done\s+){2}(todo\s+){5}$runid\s+/plan1" "$rlRun_LOG" -E
        rlRun -s "tmt clean guests --dry -v"
        rlAssertGrep "Would stop guests in run '$runid'" "$rlRun_LOG"
        rlRun -s "tmt status -vv"
        rlAssertGrep "(done\s+){2}(todo\s+){5}$runid\s+/plan1" "$rlRun_LOG" -E
    rlPhaseEnd

    rlPhaseStartTest "Specify ID"
        rlRun -s "tmt clean guests --dry -v -l"
        rlAssertGrep "Would stop guests in run '$runid'" "$rlRun_LOG"

        rlRun -s "tmt clean guests --dry -v -i $runid"
        rlAssertGrep "Would stop guests in run '$runid'" "$rlRun_LOG"

        rlRun -s "tmt status -vv"
        rlAssertGrep "(done\s+){2}(todo\s+){5}$runid\s+/plan1" "$rlRun_LOG" -E
    rlPhaseEnd

    rlPhaseStartTest "Filter by how"
        rlRun -s "tmt clean guests --dry -v --how container"
        rlAssertGrep "Would stop guests in run '$runid'" "$rlRun_LOG"

        rlRun -s "tmt clean guests --dry -v --how virtual"
        rlAssertNotGrep "Would stop guests in run '$runid'" "$rlRun_LOG"

        rlRun -s "tmt status -vv"
        rlAssertGrep "(done\s+){2}(todo\s+){5}$runid\s+/plan1" "$rlRun_LOG" -E
    rlPhaseEnd

    rlPhaseStartTest "Stop the guest"
        rlRun -s "tmt clean guests -v -i $runid"
        rlAssertGrep "Stopping guests in run '$runid'" "$rlRun_LOG"
        rlRun -s "tmt status -vv"
        rlAssertGrep "(done\s+){2}(todo\s+){4}done\s+$runid\s+/plan1" "$rlRun_LOG" -E
    rlPhaseEnd

    rlPhaseStartTest "Different root"
        rlRun "tmprun=\$(mktemp -d)" 0 "Create a temporary directory for runs"
        rlRun -s "tmt run -i $tmprun/run1 --until provision provision -h local"
        rlRun -s "tmt run -i $tmprun/run2 --until provision provision -h local"
        rlRun "tmt clean guests --workdir-root $tmprun"
        rlRun -s "tmt status --workdir-root $tmprun -vv"
        rlAssertGrep "(done\s+){2}(todo\s+){4}done\s+$tmprun/run1" "$rlRun_LOG" -E
        rlAssertGrep "(done\s+){2}(todo\s+){4}done\s+$tmprun/run2" "$rlRun_LOG" -E
    rlPhaseEnd

    rlPhaseStartTest "Test keep"
        rlRun "tmpkeep=\$(mktemp -d)" 0 "Create a temporary directory for keep test"
        rlRun -s "tmt run -i $tmpkeep/run1 --until provision provision -h local"
        rlRun -s "tmt run -i $tmpkeep/run2 --until provision provision -h local"
        rlRun "tmt clean guests --workdir-root $tmpkeep --keep 1"
        rlRun -s "tmt status --workdir-root $tmpkeep -vv"
        rlAssertGrep "(done\s+){2}(todo\s+){4}done\s+$tmpkeep/run1" "$rlRun_LOG" -E
        rlAssertGrep "(done\s+){2}(todo\s+){5}$tmpkeep/run2" "$rlRun_LOG" -E
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $runid" 0 "Remove initial run"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $tmprun" 0 "Remove a temporary directory for runs"
        rlRun "rm -r $tmpkeep" 0 "Remove the temporary directory for keep test"
    rlPhaseEnd
rlJournalEnd
