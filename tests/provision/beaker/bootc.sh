#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check bootc works well in plan way"
        rlRun -s "tmt run --dry plan --name plan/bootc$"
        rlAssertGrep 'ostreecontainer --url quay.io/fedora/custom-bootc:latest' $rlRun_LOG
        rlAssertGrep '{"auths": {"quay.io": {"auth": "dummysecret"}}}' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Check bootc works well through command line"
        rlRun -s "tmt run --dry -a provision -h beaker --bootc --bootc-image-url dummy.repo/fedora/cli-bootc:latest --bootc-registry-secret dumsecret"
        rlAssertGrep 'ostreecontainer --url dummy.repo/fedora/cli-bootc:latest' $rlRun_LOG
        rlAssertGrep '{"auths": {"dummy.repo": {"auth": "dumsecret"}}}' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Check bootc variables are specified while bootc is disabled"
        rlRun -s "tmt run --dry -a provision -h beaker --bootc-registry-secret dummysecret" 2
        rlAssertGrep 'Enable bootc with --bootc, or remove variables: bootc_registry_secret' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Check bootc-image-url is missing"
        rlRun -s "tmt run --dry -a provision -h beaker --bootc" 2
        rlAssertGrep 'bootc configuration incomplete. Missing: bootc_image_url' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
