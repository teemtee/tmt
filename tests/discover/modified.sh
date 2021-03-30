#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun 'set -o pipefail'
    rlPhaseEnd

    rlPhaseStartTest 'Command-line'
        rlRun 'tmt run -rdv discover --how fmf --ref 8329db0 \
            --modified-only --modified-ref 8329db0^ \
            plan -n features/core finish | tee output'
        rlAssertGrep 'summary: 1 test discovered' output
        rlAssertGrep '/tests/core/adjust' output
    rlPhaseEnd

    rlPhaseStartTest 'Plan'
        rlRun 'env -C data tmt run -rdv discover \
            plan -n fmf/modified finish | tee output'
        rlAssertGrep 'summary: 1 test discovered' output
        rlAssertGrep '/tests/core/adjust' output
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'rm -f output' 0 'Remove tmp file'
    rlPhaseEnd
rlJournalEnd
