#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd order"
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
    rlPhaseEnd

    rlPhaseStartTest "Test exception without option '--no-color'"
        rlRun -s "tmt run discover -h fmf -u https://127.0.0.1/nonexistent" "1-255"
        cat -A $rlRun_LOG
        #rlAssertGrep "^[[31m" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test exception with option '--no-color'"
        rlRun -s "tmt --no-color run discover -h fmf -u https://127.0.0.1/nonexistent" "1-255"
        cat -A $rlRun_LOG
        #rlAssertNotGrep "^[[31m" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'rm -rf $tmp' 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
