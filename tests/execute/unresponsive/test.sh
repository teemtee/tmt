#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test must error out if machine becomes unresponsive during execution (#3647)."
        rlRun -s "tmt run -vv -a provision -h $PROVISION_HOW" "2"
        rlAssertGrep 'fail: Failed to pull workdir from the guest.' $rlRun_LOG '-F'
        rlAssertGrep 'errr /unresponsive/test/error' $rlRun_LOG '-F'
        rlAssertGrep 'pending /unresponsive/test/pending' $rlRun_LOG '-F'
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
