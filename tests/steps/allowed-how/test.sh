#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun    "tmt -vv run --scratch -i $tmp provision -h local" 0

        rlRun -s "tmt -vv run --scratch -i $tmp provision -h local provision --allowed-how 'virtual.*'" 2
        rlAssertGrep "Suitable provision method 'local' disallowed by configuration." $rlRun_LOG
        rlAssertGrep "Unsupported provision method 'local' in the '/plan' plan." $rlRun_LOG

        rlRun -s "tmt -vv run --scratch -i $tmp provision --allowed-how '*'" 2
        rlAssertGrep "Could not compile regular expression '\\*'." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
