#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Natural order (by order field)"
        rlRun "tmt run discover --how fmf -v plan --name /natural-order finish 2>&1 | tee output"
        # Tests should be in order: test_z (10), test_a (20), test_m (30), test_b (40), test_skip (50)
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_a" output
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_b" output
        rlAssertGrep "/tests/test_skip" output

        # Verify order using line numbers
        test_z_line=$(grep -n "/tests/test_z" output | cut -d: -f1)
        test_a_line=$(grep -n "/tests/test_a" output | cut -d: -f1)
        test_m_line=$(grep -n "/tests/test_m" output | cut -d: -f1)
        test_b_line=$(grep -n "/tests/test_b" output | cut -d: -f1)

        rlRun "[ $test_z_line -lt $test_a_line ]" 0 "test_z comes before test_a"
        rlRun "[ $test_a_line -lt $test_m_line ]" 0 "test_a comes before test_m"
        rlRun "[ $test_m_line -lt $test_b_line ]" 0 "test_m comes before test_b"
    rlPhaseEnd

    rlPhaseStartTest "Test key custom order"
        rlRun "tmt run discover --how fmf -v plan --name /test-key-custom finish 2>&1 | tee output"
        # Tests should be in custom order: test_m, test_z, test_b
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_a" output
        rlAssertNotGrep "/tests/test_skip" output

        # Verify custom order
        test_m_line=$(grep -n "/tests/test_m" output | cut -d: -f1)
        test_z_line=$(grep -n "/tests/test_z" output | cut -d: -f1)
        test_b_line=$(grep -n "/tests/test_b" output | cut -d: -f1)

        rlRun "[ $test_m_line -lt $test_z_line ]" 0 "test_m comes before test_z"
        rlRun "[ $test_z_line -lt $test_b_line ]" 0 "test_z comes before test_b"
    rlPhaseEnd

    rlPhaseStartTest "Include key preserves original order"
        rlRun "tmt run discover --how fmf -v plan --name /include-preserves-order finish 2>&1 | tee output"
        # Tests should be in original order despite include order: test_z, test_m, test_b
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_a" output
        rlAssertNotGrep "/tests/test_skip" output

        # Verify preserved order (original order by order field)
        test_z_line=$(grep -n "/tests/test_z" output | cut -d: -f1)
        test_m_line=$(grep -n "/tests/test_m" output | cut -d: -f1)
        test_b_line=$(grep -n "/tests/test_b" output | cut -d: -f1)

        rlRun "[ $test_z_line -lt $test_m_line ]" 0 "test_z comes before test_m (preserved order)"
        rlRun "[ $test_m_line -lt $test_b_line ]" 0 "test_m comes before test_b (preserved order)"
    rlPhaseEnd

    rlPhaseStartTest "Exclude functionality"
        rlRun "tmt run discover --how fmf -v plan --name /exclude-functionality finish 2>&1 | tee output"
        # All tests except test_skip
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_a" output
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_skip" output
    rlPhaseEnd

    rlPhaseStartTest "Include with exclude functionality"
        rlRun "tmt run discover --how fmf -v plan --name /include-with-exclude finish 2>&1 | tee output"
        # Should include test_z, test_a, test_m, test_b but exclude test_skip
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_a" output
        rlAssertGrep "/tests/test_m" output
        rlAssertGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_skip" output
    rlPhaseEnd

    rlPhaseStartTest "Test key repetition"
        rlRun "tmt run discover --how fmf -v plan --name /test-key-repeat finish 2>&1 | tee output"
        # Should have test_z twice and test_a once
        rlAssertGrep "/tests/test_z" output
        rlAssertGrep "/tests/test_a" output
        rlAssertNotGrep "/tests/test_m" output
        rlAssertNotGrep "/tests/test_b" output
        rlAssertNotGrep "/tests/test_skip" output

        # Count occurrences of test_z (should appear twice)
        test_z_count=$(grep -c "/tests/test_z" output)
        rlRun "[ $test_z_count -eq 2 ]" 0 "test_z appears twice"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
