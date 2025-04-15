#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "export TMT_WORKDIR_ROOT=$tmp"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test must error out if machine becomes unresponsive during execution (#3630)."
        rlRun -s "tmt run -vv -a provision -h $PROVISION_HOW" "2"
        rlAssertGrep 'fail: Failed to pull workdir from the guest.' $rlRun_LOG '-F'
        rlAssertGrep 'errr /unresponsive/test/error' $rlRun_LOG '-F'
        rlAssertGrep 'pending /unresponsive/test/pending' $rlRun_LOG '-F'
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
