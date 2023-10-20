#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

set -o pipefail

rlJournalStart
    rlPhaseStartTest
        rlRun "rlImport --all"
        rlRun "first"
    rlPhaseEnd
rlJournalEnd
