#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
    rlPhaseEnd

    rlPhaseStartTest "Check guest environment variables are set correctly"
        rlRun -s "tmt -vvv run plan --name /plans/guest-only"

        rlAssertGrep "default-0:foo" $rlRun_LOG
        rlAssertGrep "default-1:bar" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Check environment variables from guest are overridden by test variables"
        rlRun -s "tmt -vvv run plan --name /plans/test-override"

        rlAssertGrep "default-0:baz" $rlRun_LOG
        rlAssertGrep "default-1:baz" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
