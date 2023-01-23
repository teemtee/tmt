#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

set -o pipefail

rlJournalStart
    rlPhaseStartSetup
    rlPhaseEnd

    rlPhaseStartTest "Smoke test, list plans"
        rlRun -s "./smoke.py"
        rlAssertGrep "/plans/features/core" $rlRun_LOG
        rlAssertGrep "/plans/features/basic" $rlRun_LOG
        rlAssertNotGrep "/interactive-anchor-plan" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Smoke test, list plans from different tree"
        rlRun -s "./smoke-explicit-tree.py"
        rlAssertNotGrep "/tests/core" $rlRun_LOG
        rlAssertNotGrep "/tests/unit" $rlRun_LOG
        rlAssertGrep "/interactive-anchor-plan" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
    rlPhaseEnd
rlJournalEnd
