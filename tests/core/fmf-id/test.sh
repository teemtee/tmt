#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt plan -vvvv show /plan-with-valid-ref"
        rlAssertNotGrep "warn:" $rlRun_LOG
        rlAssertGrep "ref branch-or-tag-ref" $rlRun_LOG
        rlAssertGrep "ref 8deadbeaf8" $rlRun_LOG

        rlRun -s "tmt plan -vvvv show /plan-with-invalid-ref" 2
        rlAssertGrep "warn: /plan-with-invalid-ref:discover .* is not valid under any of the given schemas" $rlRun_LOG
        rlAssertGrep "Failed to load step data for DiscoverFmfStepData: Field 'DiscoverFmfStepData:ref' must be unset or a string, 'int' found." $rlRun_LOG

        rlRun -s "tmt plan -vvvv show /remote-plan-with-valid-ref"

        rlRun -s "tmt plan -vvvv show /remote-plan-with-invalid-ref" 2
        rlAssertGrep "warn: /remote-plan-with-invalid-ref:plan.import.ref - 12345678 is not of type 'string'" $rlRun_LOG

        rlRun -s "tmt test -vvvv show /test-with-valid-ref"
        rlAssertNotGrep "warn:" $rlRun_LOG
        rlRun "grep -Pzo \"(?s)- ref: branch-or-tag-ref.*?\\s*type: library\" $rlRun_LOG > /dev/null"
        rlRun "grep -Pzo \"(?s)- ref: 8deadbeaf8.*?\\s*type: library\" $rlRun_LOG > /dev/null"
        rlAssertGrep "- some-package" $rlRun_LOG

        rlRun -s "tmt test -vvvv show /test-with-invalid-ref" 2
        rlAssertGrep "warn: /test-with-invalid-ref:require .* is not valid under any of the given schemas" $rlRun_LOG
        rlAssertGrep "Field 'ref' must be unset or a string, 'int' found." $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
