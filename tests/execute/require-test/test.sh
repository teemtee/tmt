#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "set -o pipefail"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "All required tests should be executed"
        rlRun -s "tmt run --id $run --scratch -vvv plan -n /plans/good" 1
        rlAssertGrep "summary: 7 tests selected" "$rlRun_LOG"
        rlAssertGrep "summary: 5 tests executed, 2 tests skipped" "$rlRun_LOG"
        rlAssertGrep "total: 3 tests passed, 2 tests failed and 2 tests skipped" "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Required test was skipped"
        rlRun -s "tmt run --id $run --scratch -vvv plan -n /plans/skipped" 2
        rlAssertGrep "summary: 5 tests selected" "$rlRun_LOG"
        rlAssertGrep "summary: 3 tests executed, 2 tests skipped" "$rlRun_LOG"
        rlAssertGrep "Required test '/second/tests/skip' on guest 'default-0' was skipped." "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'popd'
        rlRun "rm -rf $run" 0 'Remove run directory'
    rlPhaseEnd
rlJournalEnd
