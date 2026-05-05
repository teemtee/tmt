#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'set -o pipefail'
        rlRun "run=\$(mktemp -d)" 0 "Create a run directory"
    rlPhaseEnd

    rlPhaseStartTest "Remote"
        rlRun "pushd modified"
        rlRun -s "tmt run -v --scratch -i $run discover plan -n /plan/remote"
        rlAssertGrep "summary: 2 tests selected" "$rlRun_LOG"
        rlAssertGrep "/tests/modified-only$" "$rlRun_LOG" -E
        rlAssertGrep "/tests/modified-only/sub$" "$rlRun_LOG" -E
        rlAssertNotGrep "/tests/modified-only-skip$" "$rlRun_LOG" -E
        rlRun "popd"
    rlPhaseEnd

    rlPhaseStartTest 'Command-line'
        rlRun -s 'tmt run -rdv discover --how fmf --ref 8329db0 \
            --modified-only --modified-ref 8329db0^ \
            plan -n features/core finish >/dev/null'
        rlAssertGrep 'summary: 1 test selected' "$rlRun_LOG"
        rlAssertGrep '/tests/core/adjust' "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest 'Plan'
        rlRun -s 'env -C data tmt run -rdv discover \
            plan -n fmf/modified finish >/dev/null'
        rlAssertGrep 'summary: 1 test selected' "$rlRun_LOG"
        rlAssertGrep '/tests/core/adjust' "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest 'No changes'
        rlRun -s 'env -C data tmt run -rdv discover \
            plan -n fmf/empty-modified >/dev/null'
        rlAssertGrep 'summary: 0 tests selected' "$rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove the run directory"
    rlPhaseEnd
rlJournalEnd
