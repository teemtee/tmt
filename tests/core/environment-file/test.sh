#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Run pytest session"
        rlRun "python3 -m pytest -svv"
    rlPhaseEnd
rlJournalEnd
