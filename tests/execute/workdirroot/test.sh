#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "export TMT_WORKDIR_ROOT=$tmp"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test must pass with workdir root changing to non-default"
        rlRun -s "tmt run -vv -a provision -h $PROVISION_HOW" "0"
        rlAssertGrep $tmp $rlRun_LOG '-F'
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
