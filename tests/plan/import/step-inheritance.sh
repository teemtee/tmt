#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd step-inheritance"
    rlPhaseEnd

    rlPhaseStartTest "Test discover step append mode"
        rlRun -s "tmt plan show /discover-append"
        # Should show both remote and local discover configurations
        rlAssertGrep "how shell" $rlRun_LOG     # local discover
        rlAssertGrep "Additional test from local plan" $rlRun_LOG

        # Export and verify inheritance
        rlRun -s "tmt plan export /discover-append"
        rlAssertGrep "how: shell" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test discover step replace mode"
        rlRun -s "tmt plan show /discover-replace"
        # Should show only local discover configuration (replacing remote)
        rlAssertGrep "how shell" $rlRun_LOG      # local discover
        rlAssertGrep "Replacement test from local plan" $rlRun_LOG

        # Export and verify inheritance
        rlRun -s "tmt plan export /discover-replace"
        rlAssertGrep "how: shell" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test multiple adjust fields"
        rlRun -s "tmt plan show /multiple-adjust"
        # Should show local finish (append) and report (replace)
        rlAssertGrep "Local finish" $rlRun_LOG
        rlAssertGrep "/tmp/local-finish.xml" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test conditional adjust-plans with when/because"
        rlRun -s "tmt plan show -vv /conditional-adjust"
        # Should show conditional adjustments applied
        rlAssertGrep "/tmp/conditional-results.xml" $rlRun_LOG

        # Export and check for when/because clauses (in original plan data)
        rlRun -s "tmt plan export /conditional-adjust"
        rlAssertGrep "how: junit" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Schema validation"
        # Ensure all adjust-plans configurations pass schema validation
        rlRun "tmt lint"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
