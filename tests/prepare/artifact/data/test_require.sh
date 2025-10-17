#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test artifact installation on Fedora"
        rlRun "rpm -q make" 0 "Check that make is installed"
        rlRun -s "dnf info --installed make"
        # TODO: Fix the grep check with the appropriate repository source
        rlAssertGrep "^From repository\s*:\s*.*$" $rlRun_LOG
    rlPhaseEnd
rlJournalEnd
