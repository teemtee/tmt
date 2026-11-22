#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check restart and reboot variables"
        for variable in TMT_REBOOT_COUNT RSTRNT_REBOOTCOUNT REBOOTCOUNT; do
            rlLog "$variable=${!variable}"
            rlRun "[[ -n '${!variable}' ]]" 0 \
                "Reboot count variable '$variable' must be defined."
        done

        for variable in TMT_TEST_RESTART_COUNT; do
            rlLog "$variable=${!variable}"
            rlRun "[[ -n '${!variable}' ]]" 0 \
                "Test restart count variable '$variable' must be defined."
        done
    rlPhaseEnd

    rlPhaseStartTest "Run a dummy test"
        # Reboot the guest behind tmt's back and let the reboot kill the
        # test session. tmt sees exit code 255 only after the guest went
        # down, therefore the reconnect always has to wait for the guest
        # to come back. Stopping sshd first makes sure a new SSH master
        # cannot connect to the guest while it is shutting down.
        if [ "${OUT_OF_BAND_REBOOT:-no}" = "yes" ] && [ "$TMT_TEST_RESTART_COUNT" == "0" ]; then
            rlRun "systemctl stop sshd"
            rlRun "systemctl reboot"
            sleep 120
            rlFail "The guest did not reboot"
            exit 1
        fi

        rlRun "sync"

        # Fail two times - each time triggering a test restart - and pretend
        # things are fine in the third round.
        if [ "$TMT_TEST_RESTART_COUNT" == "0" ]; then
            exit 79

        elif [ "$TMT_TEST_RESTART_COUNT" == "1" ]; then
            exit 79

        elif [ "$TMT_TEST_RESTART_COUNT" == "2" ]; then
            rlRun "/bin/true"
        fi
    rlPhaseEnd
rlJournalEnd
