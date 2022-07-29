#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    if [[ $TMT_REBOOT_COUNT -eq 0 ]]; then
        rlPhaseStartTest "Before reboot"
            rlRun "cp sleeper.service /usr/lib/systemd/system/"
            rlRun "systemctl enable sleeper.service"
            rlRun -l "who -b"
            rlRun "tmt-reboot"
        rlPhaseEnd
    else
        rlPhaseStartTest "After reboot"
            rlRun -l "who -b"
            # TODO fix to assert proper status (oneshot finished)
            rlRun "systemctl status sleeper" "0-255"
        rlPhaseEnd
    fi
rlJournalEnd
