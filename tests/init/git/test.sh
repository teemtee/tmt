#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "git init"
    rlPhaseEnd

    rlPhaseStartTest "Dry"
        rlRun -s "tmt init -t base --dry"
        rlAssertGrep "Tree .* would be initialized." "${rlRun_LOG}"
        rlAssertGrep "Path .* would be added to git index." "${rlRun_LOG}"
    rlPhaseEnd

    rlPhaseStartTest "Create"
        rlRun -s "tmt init -t base"
        rlAssertGrep "Tree .* initialized." "${rlRun_LOG}"
        rlAssertGrep "Path .* added to git index." "${rlRun_LOG}"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
