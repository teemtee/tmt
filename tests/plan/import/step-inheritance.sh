#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd step-inheritance"
    rlPhaseEnd

    rlPhaseStartTest "Test report step append mode"
        rlRun -s "tmt plan show /test-report-append"
        # Should show both remote and local report configurations
        rlAssertGrep "how junit" $rlRun_LOG     # local report
        rlAssertGrep "/tmp/local-results.xml" $rlRun_LOG

        # Export and verify inheritance
        rlRun "tmt plan export /test-report-append > append-export.yaml"
        rlAssertGrep "how: junit" append-export.yaml
    rlPhaseEnd

    rlPhaseStartTest "Test report step replace mode"
        rlRun -s "tmt plan show /test-report-replace"
        # Should show only local report configuration (replacing remote)
        rlAssertGrep "how html" $rlRun_LOG      # local report
        rlAssertGrep "/tmp/replacement.html" $rlRun_LOG

        # Export and verify inheritance
        rlRun "tmt plan export /test-report-replace > replace-export.yaml"
        rlAssertGrep "how: html" replace-export.yaml
    rlPhaseEnd

    rlPhaseStartTest "Test no step inheritance (control)"
        rlRun -s "tmt plan show /test-no-inheritance"
        # Should show only remote plan configuration without local step inheritance
        rlAssertNotGrep "/tmp/ignored.xml" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test alternative enum values"
        rlRun -s "tmt plan show /test-alternative-enum"
        # Test alternative "append" enum value (should work same as "+")
        rlAssertGrep "Local finish with append enum" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Test multiple adjust fields"
        rlRun -s "tmt plan show /test-multiple-adjust"
        # Should show local finish (append) and report (replace)
        rlAssertGrep "Local prepare" $rlRun_LOG
        rlAssertGrep "/tmp/local-finish.xml" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Schema validation"
        # Ensure all adjust-plans configurations pass schema validation
        rlRun "tmt lint"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -f append-export.yaml replace-export.yaml"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
