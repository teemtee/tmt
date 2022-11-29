#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

METHODS="${METHODS:-virtual}"

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $tmp"
    rlPhaseEnd

    for method in $METHODS; do

    rlPhaseStartTest "provision $method"
        rlRun -s "tmt run -r plans --default provision -h $method prepare -h shell --script 'touch X' login -k -c 'test -e X; echo @@@$?@@@' finish"
        rlAssertGrep '@@@0@@@' $rlRun_LOG
    rlPhaseEnd

    done

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalEnd
