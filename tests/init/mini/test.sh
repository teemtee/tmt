#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartTest "Empty"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun -s "tmt init -n"
        rlAssertNotExists ".fmf/version"
        rlAssertGrep "Would initialize the fmf tree root" "${rlRun_LOG}"
        rlRun -s "tmt init"
        rlAssertExists ".fmf/version"
        rlAssertGrep "Initialized the fmf tree root" "${rlRun_LOG}"
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd

    rlPhaseStartTest "Mini"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun -s "tmt init -t mini -n"
        rlAssertGrep "Plan directory .* would be created." "${rlRun_LOG}"
        rlAssertNotExists "plans/example.fmf"
        rlRun -s "tmt init -t mini"
        rlAssertGrep "Initialized the fmf tree root" "${rlRun_LOG}"
        rlAssertGrep "Applying template 'mini'." "${rlRun_LOG}"
        rlAssertGrep "Plan directory .* created." "${rlRun_LOG}"
        rlAssertExists "plans/example.fmf"
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
