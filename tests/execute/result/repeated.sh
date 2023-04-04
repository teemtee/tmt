#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd repeated"
    rlPhaseEnd

    rlPhaseStartTest "Running tests separately"
        rlRun -s "tmt run -v -i $run" 1

        # Check output
        rlAssertGrep "pass /test" "$rlRun_LOG"
        rlAssertGrep "fail /test" "$rlRun_LOG"
        rlAssertGrep "1 test passed and 1 test failed" "$rlRun_LOG"

        # Check results.yaml
        results="$run/plan/execute/results.yaml"
        rlAssertGrep "result: fail" "$results"
        rlAssertGrep "result: pass" "$results"
        rlAssertGrep "test-1/output.txt" "$results"
        rlAssertGrep "test-2/output.txt" "$results"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r ${run}" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
