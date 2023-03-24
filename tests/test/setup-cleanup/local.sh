#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Show curl tests"
        rlRun -s "tmt tests show tests/curl -v"
        rlAssertGrep "setup" $rlRun_LOG
        rlAssertGrep "cleanup" $rlRun_LOG
        rlAssertGrep "./setup_" $rlRun_LOG
        rlAssertGrep "./remove_" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Run tests with local setup and cleanup scripts"
        rlRun -s "tmt run -a -r -vv provision -h container tests -n /tests/curl"
        rlAssertGrep "cmd: ./setup_" $rlRun_LOG
        rlAssertGrep "cmd: ./remove_" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
