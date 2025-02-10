#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init"
        rlRun "mkdir -p $tmp/testcloud/images"
        rlRun "touch $tmp/testcloud/images/dummy"

    rlPhaseStartTest "clean images "
        rlRun "tmt clean images -v --workdir-root $tmp"
	rlAssertNotExists "$tmp/testcloud/images/dummy"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
