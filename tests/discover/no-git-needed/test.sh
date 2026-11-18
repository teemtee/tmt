#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "plan_run=\$(mktemp -d)" 0 "Create plan-configured run directory"
        rlRun "set -o pipefail"
        rlRun "pushd data"
        rlRun "git init"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "tmt --root tests run --keep -i $run" 0
        rlAssertNotExists "$run/plan/discover/default-0/tests/foo"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "tmt --root tests run --keep --scratch -ai $run discover -h fmf --sync-repo" 0
        rlAssertExists "$run/plan/discover/default-0/tests/foo"
    rlPhaseEnd

    rlPhaseStartTest "sync-repo configured in the plan"
        rlRun "tmt --root tests run --keep --scratch -i $plan_run discover plan -n /sync-repo" 0
        rlAssertExists "$plan_run/plan/sync-repo/discover/default-0/tests/foo"
        rlAssertExists "$plan_run/plan/sync-repo/discover/default-0/tests/.git"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -r $run $plan_run .git" 0 "Remove run directories"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
