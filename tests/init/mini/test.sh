#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun -s "tmt init -n"
        rlAssertNotExists ".fmf/version"
        rlAssertGrep "Tree .* would be initialized." "${rlRun_LOG}"
        rlRun -s "tmt init"
        rlAssertExists ".fmf/version"
        rlAssertGrep "Tree .* initialized." "${rlRun_LOG}"
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun -s "tmt init -t mini -n"
        rlAssertGrep "Directory .* would be created." "${rlRun_LOG}"
        rlAssertNotExists "plans/example.fmf"
        rlRun -s "tmt init -t mini"
        rlAssertGrep "Tree .* initialized." "${rlRun_LOG}"
        rlAssertGrep "Applying template 'mini'." "${rlRun_LOG}"
        rlAssertGrep "Directory .* created." "${rlRun_LOG}"
        rlAssertExists "plans/example.fmf"
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd

rlJournalEnd
