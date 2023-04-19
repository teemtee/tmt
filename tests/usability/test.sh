#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test command abbreviation"
        rlRun -s "tmt run --rm pl disc -h local 2>&1" "1-255"
        rlAssertGrep "Unsupported discover method 'local'" $rlRun_LOG
        rlRun -s "tmt run --rm pl disc provi -h local"
        rlRun "grep -A1 discover $rlRun_LOG | grep 'how: fmf'"
        rlRun "grep -A1 provision $rlRun_LOG | grep 'how: local'"

        rlRun -s "tmt run --rm pl disc -vvvddd -h local 2>&1" "1-255"
        rlAssertGrep "Unsupported discover method 'local'" $rlRun_LOG
        rlRun -s "tmt run --rm pl disc -vvvddd provi -h local"
        rlRun "grep -A1 discover $rlRun_LOG | grep 'how: fmf'"
        rlRun "grep -A1 provision $rlRun_LOG | grep 'how: local'"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
