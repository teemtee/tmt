#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

function check() {
    # Space-separated test names on a single line
    tests=$(grep '^  */tests/' "$rlRun_LOG" | sed 's/^ *//' | tr '\n' ' ' | sed 's/ $//')
    rlAssertEquals "Check expected tests" "$tests" "$1"
}

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Natural order (by order field)"
        rlRun "tmt run discover --how fmf -v plan --name /natural-order finish 2>&1 | tee output"
        # Tests should be in order: test_z (10), test_a (20), test_m (30), test_b (40), test_skip (50)
        check "/tests/test_z /tests/test_a /tests/test_m /tests/test_b /tests/test_skip"
    rlPhaseEnd

    rlPhaseStartTest "Test key custom order"
        rlRun "tmt run discover --how fmf -v plan --name /test-key-custom finish 2>&1 | tee output"
        # Tests should be in custom order: test_m, test_z, test_b
        check "/tests/test_m /tests/test_z /tests/test_b"
    rlPhaseEnd

    rlPhaseStartTest "Include key preserves original order"
        rlRun "tmt run discover --how fmf -v plan --name /include-preserves-order finish 2>&1 | tee output"
        # Tests should be in original order despite include order: test_z, test_m, test_b
        check "/tests/test_z /tests/test_m /tests/test_b"
    rlPhaseEnd

    rlPhaseStartTest "Exclude functionality"
        rlRun "tmt run discover --how fmf -v plan --name /exclude-functionality finish 2>&1 | tee output"
        # All tests except test_skip
        check "/tests/test_z /tests/test_a /tests/test_m /tests/test_b"
    rlPhaseEnd

    rlPhaseStartTest "Include with exclude functionality"
        rlRun "tmt run discover --how fmf -v plan --name /include-with-exclude finish 2>&1 | tee output"
        # Should include test_z, test_a, test_m, test_b but exclude test_skip
        check "/tests/test_z /tests/test_a /tests/test_m /tests/test_b"
    rlPhaseEnd

    rlPhaseStartTest "Test key repetition"
        rlRun "tmt run discover --how fmf -v plan --name /test-key-repeat finish 2>&1 | tee output"
        # Should have test_z twice and test_a once
        check "/tests/test_z /tests/test_a /tests/test_z"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
