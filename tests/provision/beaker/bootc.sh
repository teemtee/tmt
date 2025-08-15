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

    rlPhaseStartTest "bootc Configuration Validation"
        # Test missing required fields
	rlRun -s "tmt run --dry plan --name plan/bootc-invalid$" 2 "Should fail with missing config"
	rlAssertGrep "bootc configuration incomplete" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "bootc Image URL Validation"
        # Test invalid image URLs
	rlRun -s "tmt run --dry plan --name plan/bootc-bad-url$" 2 "Should fail with invalid URL"
	rlAssertGrep "Invalid image URL" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
