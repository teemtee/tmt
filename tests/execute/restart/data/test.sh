#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
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
