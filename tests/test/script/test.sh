#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Normal test metadata"
        rlRun -s "tmt tests ls /pos" 0
        rlAssertGrep "/tests/foo/pos" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Malformed test metadata"
        rlRun -s "tmt tests ls /neg" "1-255"
        rlAssertGrep "Field '/tests/foo/neg:test' must be a string, 'bool' found" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
