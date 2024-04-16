#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest
        rlRun "bash --help" 0 "Check help message"
        rlLog "IN_PLACE_UPGRADE=$IN_PLACE_UPGRADE"
        # Uses upgrade task with dummy package as require - teemtee/upgrade/tree/main/tasks
        if [[ "$IN_PLACE_UPGRADE" == "new" ]]; then
            rlRun "rpm -q dummy-test-package-crested" 0 "Check upgrade task dependency"
        fi
        # Remove beakerlib to make sure it will be installed as upgrade task framework
        if [[ "$REMOVE_BEAKERLIB" == "1" ]] && [[ "$IN_PLACE_UPGRADE" == "old" ]]; then
            rlRun "dnf remove beakerlib --noautoremove -y"
        fi
    rlPhaseEnd
rlJournalEnd
