#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

# The manual instructions in data/test.md contain a code block which
# would create this file. It must never be executed by tmt.
SENTINEL="/tmp/tmt-manual-test-was-executed"

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "rm -f $SENTINEL" 0 "Make sure the sentinel file does not exist"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Manual and automated tests together"
        rlRun -s "tmt run --scratch --id $run --all plan --name /plans/mixed" 0
        rlAssertGrep "2 tests selected" $rlRun_LOG
        rlAssertGrep "Manual test '/tests/manual' cannot be executed by tmt." $rlRun_LOG
        rlAssertGrep "1 test executed, 1 test skipped" $rlRun_LOG

        results="$run/plans/mixed/execute/results.yaml"
        rlRun "yq -e '.[] | select(.name == \"/tests/automated\") | .result == \"pass\"' $results" \
            0 "The automated test passed"
        rlRun "yq -e '.[] | select(.name == \"/tests/manual\") | .result == \"skip\"' $results" \
            0 "The manual test was skipped"
        rlRun "yq -e '.[] | select(.name == \"/tests/manual\") | .note[0] == \"manual test, not executed by tmt\"' $results" \
            0 "The skip result explains why the test was not executed"
    rlPhaseEnd

    rlPhaseStartTest "A plan with manual tests only"
        rlRun -s "tmt run --scratch --id $run --all plan --name /plans/manual-only" 4
        rlAssertGrep "1 test skipped" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Manual test discovered by the shell plugin"
        rlRun -s "tmt run --scratch --id $run --all plan --name /plans/shell" 4
        rlAssertGrep "1 test selected" $rlRun_LOG
        rlAssertGrep "Manual test '/manual' cannot be executed by tmt." $rlRun_LOG

        results="$run/plans/shell/execute/results.yaml"
        rlRun "yq -e '.[0].result == \"skip\"' $results" 0 "The manual test was skipped"
    rlPhaseEnd

    rlPhaseStartTest "Manual test requested as a required test"
        rlRun -s "tmt run --scratch --id $run --all plan --name /plans/required" 2
        rlAssertGrep "Required test '/tests/manual' on guest '.*' was skipped." $rlRun_LOG -E
    rlPhaseEnd

    rlPhaseStartTest "The manual instructions are never executed"
        rlAssertNotExists "$SENTINEL"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
