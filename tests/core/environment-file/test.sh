#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Run pytest session"
        rlRun "pytest -svv"
    rlPhaseEnd
rlJournalEnd
