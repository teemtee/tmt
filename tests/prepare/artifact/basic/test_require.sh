#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Test artifact installation on Fedora"
        # Check that make comes from tmt-artifact-shared
        rlRun "rpm -q make" 0 "Check that make is installed"
        rlRun -s "dnf info --installed make"
        rlAssertGrep "From repo(sitory)?\s*:\s*tmt-artifact-shared" $rlRun_LOG -E

        # Verify docker-ce repository is enabled
        rlRun -s "dnf repo info docker-ce-stable"
        rlAssertGrep "Status.*: enabled" $rlRun_LOG

    rlPhaseEnd
rlJournalEnd
