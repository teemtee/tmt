#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    for method in ${METHODS:-container}; do
        rlPhaseStartTest "Test ($method)"
            rlRun "tmt run -v plans --default provision -h $method"
            rlRun "tmt run --last --remove plans --default finish"
        rlPhaseEnd
    done
rlJournalEnd
