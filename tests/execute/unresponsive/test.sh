#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
    rlPhaseEnd

    rlPhaseStartTest "Test must error out if machine becomes unresponsive during execution (#3647)."
        rlRun -s "tmt run -vv -a provision -h $PROVISION_HOW" "2"
        rlAssertGrep 'Failed to verify rsync presence|Failed to push workdir' $rlRun_LOG '-E'
        rlAssertGrep 'errr /unresponsive/test/error' $rlRun_LOG '-F'
        rlAssertGrep 'pending /unresponsive/test/pending' $rlRun_LOG '-F'
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
