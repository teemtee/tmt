#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check bootc works well"
        rlRun -s "tmt run --dry plan --name plan/bootc$"

        rlAssertGrep 'ostreecontainer --url quay.io/fedora/custom-bootc:latest' $rlRun_LOG
        rlAssertGrep 'dummysecret' $rlRun_LOG
        rlAssertGrep '{"auths": {"quay.io": {"auth": "dummysecret"}}}' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
