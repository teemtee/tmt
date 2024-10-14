#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "tmt='tmt run -ar provision -h local execute -h tmt -s '"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init -t mini"
    rlPhaseEnd

    rlPhaseStartTest "Skipped"
        rlRun -s "$tmt true login -w fail -c true"
        rlAssertGrep "Skipping interactive" $rlRun_LOG
        rlAssertNotGrep "Starting interactive" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Enabled"
        rlRun -s "$tmt false login -w fail -c true" 1
        rlAssertNotGrep "Skipping interactive" $rlRun_LOG
        rlAssertGrep "Starting interactive" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
