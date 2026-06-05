#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Debug Test"
        rlRun "tmt run --remove --until finish plans -n /plan provision -h container"
        rlRun "tmt run --last report"
        rlRun "tmt run --last login --command /bin/true"
        rlRun "tmt run --last cleanup"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
