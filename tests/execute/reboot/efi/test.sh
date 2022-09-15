#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check reboot variables"
        for variable in TMT_REBOOT_COUNT RSTRNT_REBOOTCOUNT REBOOTCOUNT; do
            rlLog "$variable=${!variable}"
            rlRun "[[ -n '${!variable}' ]]" 0 \
                "Reboot count variable '$variable' must be defined."
        done
    rlPhaseEnd

    # Before
    if [ "$TMT_REBOOT_COUNT" == "0" ]; then
        rlPhaseStartTest "Before reboot"
            if [ $(command -v efibootmgr) &>/dev/null ]; then
                rlLog "efibootmgr installed."
                rlRun "current=$(efibootmgr | awk '/BootCurrent/ { print $2 }')" 0 "Ascertain BootCurrent value."
                rlLog "BootCurrent=$current"
            fi
            rlRun "tmt-reboot" 0 "Reboot using 'tmt-reboot'."
            # Add sleep to check that the test is killed by tmt-reboot
            rlRun "sleep 3600"
        rlPhaseEnd

    # First
    elif [ "$TMT_REBOOT_COUNT" == "1" ]; then
        rlPhaseStartTest "After first reboot"
            rlRun "syslog=/var/log/messages"
            rlRun "count=$(grep \"efibootmgr -n $current\" $syslog | wc -l)"
            rlAssertEqual "Ensure BootNext set to BootCurrent value." $count 1
            rlRun "tmt-reboot -e" 0 "Reboot using 'tmt-reboot -e'."
        rlPhaseEnd

    # Second
    elif [ "$TMT_REBOOT_COUNT" == "2" ]; then
        rlPhaseStartTest "After second reboot"
            rlRun "count=$(grep \"efibootmgr -n $current\" $syslog | wc -l)"
            rlAssertEqual "Ensure BootNext set to BootCurrent value." $count 1
        rlPhaseEnd

    # Weird
    else
        rlPhaseStartTest "Weird"
            rlFail "Unexpected reboot count '$TMT_REBOOT_COUNT'."
        rlPhaseEnd
    fi
rlJournalEnd
