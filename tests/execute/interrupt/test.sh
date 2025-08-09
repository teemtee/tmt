#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
    rlPhaseEnd

    rlPhaseStartTest "Verify tmt correctly interrupts a test and all following tests"
        # Spawn the tmt process, in the background - tmt is expected to run the plan and test,
        # and reach a `sleep 3600`.
        tmt run -i $run -dddvvva provision -h $PROVISION_HOW plan -n /plan &> tmt.output &
        tmt_pid="$!"

        rlLogInfo "Running \"tmt run -i $run -dddvvva provision -h $PROVISION_HOW plan -n /plan &> tmt.output\" in the background"
        rlLogInfo "Background tmt PID is $tmt_pid"

        # Now we wait for the test to go to sleep...
        while true; do
            rlLogInfo "checking output for 'sleep 3600'..."

            current_tail="$(tail -n 10 tmt.output)"

            rlLogDebug "Current tmt output tail:\n$current_tail"

            if [[ "$current_tail" == *"+++ sleep 3600"* ]]; then
                rlLogInfo "found!"
                break;
            fi

            sleep 10
        done

        rlRun "kill -SIGINT $tmt_pid"
        wait "$tmt_pid"

        rlAssertGrep "warn: Interrupt requested via SIGINT signal." "$run/log.txt"

        rlAssertGrep "errr /tests/d" "$run/log.txt"
        rlAssertGrep "pending /tests/do-not/1" "$run/log.txt"
        rlAssertGrep "pending /tests/do-not/2" "$run/log.txt"

        rlAssertEquals "check expected outcomes" \
            "$(yq -r '[sort_by(.name) | .[] | "\(.name):\(.result)"] | join(" ")' ${run}/plan/execute/results.yaml)" \
            "/tests/do:error /tests/do-not/1:pending /tests/do-not/2:pending"

        rlAssertEquals "results should record the test aborted" \
            "$(yq -r '[.[] | .check[] | .name] | sort | join(" ")' ${run}/plan/execute/results.yaml)" \
            "internal/interrupt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
