#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "export TMT_NO_COLOR=1"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Execute without push after manual modification"
        # Run the test that simulates manual modification scenario
        rlRun -s "./execute-no-push.exp" 0 "Run execute without push test"

        # Verify that the modified version was executed (not overwritten by host)
        rlAssertGrep "^MODIFIED_ON_GUEST$" $rlRun_LOG

        test_count=$(grep -c 'ORIGINAL_HOST_VERSION' $rlRun_LOG)
        rlAssertEquals "The original test run twice" "$test_count" "2"

        # Verify the interactive session completed properly
        rlAssertGrep "Run .* successfully finished. Bye for now!" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
