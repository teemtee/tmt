#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'set -o pipefail'
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
rlJournalEnd
