#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Show timeout tests"
        rlRun -s "tmt tests show tests/timeout -v"
        rlAssertGrep "setup" $rlRun_LOG
        rlAssertGrep "cleanup" $rlRun_LOG
        rlAssertGrep "./setup_" $rlRun_LOG
        rlAssertGrep "./sleep_" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Run tests with local setup and cleanup scripts"
        rlRun -s "tmt run -a -r -vv provision -h container tests -n /tests/timeout" 2
        rlAssertGrep "cmd: ./setup_" $rlRun_LOG
        rlAssertGrep "./sleep_" $rlRun_LOG
	rlAssertGrep "(timeout)" $rlRun_LOG
	rlAssertGrep "2 errors" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
