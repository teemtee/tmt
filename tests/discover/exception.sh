#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

PTTY_WRAPPER="../execute/tty/ptty-wrapper"

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
    rlPhaseEnd

    rlPhaseStartTest "Test exception without option '--no-color'"
        rlRun -s "$PTTY_WRAPPER tmt            run --id $tmp --scratch discover -h fmf -u https://127.0.0.1/nonexistent" "1-255"
        cat -A $rlRun_LOG
        rlRun "grep -aP '\e\[31m' $rlRun_LOG"
    rlPhaseEnd

    rlPhaseStartTest "Test exception with option '--no-color'"
        rlRun -s "$PTTY_WRAPPER tmt --no-color run --id $tmp --scratch discover -h fmf -u https://127.0.0.1/nonexistent" "1-255"
        cat -A $rlRun_LOG
        rlRun "grep -aP '\e\[31m' $rlRun_LOG" 1
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun 'rm -rf $tmp' 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
