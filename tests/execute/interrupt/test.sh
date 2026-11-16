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

        # Now we wait for the test to go to sleep. The `sleep 3600` command
        # comes from the `/tests/do` test defined in data/main.fmf, and tmt
        # traces it because the test body turns on `set -x`.
        attempts=0
        while true; do
            rlLogInfo "checking output for 'sleep 3600'..."

            current_tail="$(tail -n 10 tmt.output)"

            rlLogDebug "Current tmt output tail:\n$current_tail"

            # The command is traced by bash, one "+" per level of shell nesting,
            # and tmt prints that line with an indent and a ``stdout:`` label,
            # so the run of "+" signs is not at the start of the line. Match
            # whichever count of them arrives, and require it to stand as its
            # own token so ``sleep 36000`` or ``x=+ sleep 3600`` are not taken
            # for the trace. The whole file is searched, not just the tail,
            # because the line scrolls out of the last ten lines as soon as
            # tmt writes more output.
            if grep -a -qE '(^|[[:space:]])\+{1,} sleep 3600($|[[:space:]])' tmt.output; then
                rlLogInfo "found!"
                break;
            fi

            # 180 checks give 179 sleeps of 10 seconds, about 1790 s. With virtual
            # provisioning this test is given 40 minutes, so the bound is reached
            # roughly ten minutes before the deadline and the failure is reported
            # while the phase is still running. The bound limits the polling only,
            # the interrupt that follows is not covered by it. The deadline this
            # test gets under local provisioning is 20 minutes, shorter than the
            # bound, so there the deadline ends the phase first and this bound
            # only keeps the loop itself finite.
            attempts=$((attempts + 1))
            if [ "$attempts" -ge 180 ]; then
                tail_output="${TMT_TEST_DATA:-.}/tmt.output-tail.txt"
                tail -n 50 tmt.output > "$tail_output"
                rlFail "the test did not reach 'sleep 3600' in 180 checks, the last output is in $tail_output"
                break
            fi

            sleep 10
        done

        rlRun "kill -SIGINT $tmt_pid" 0,1
        wait "$tmt_pid"

        rlAssertGrep "warn: Interrupt requested via SIGINT signal." "$run/log.txt"

        rlAssertGrep "errr /tests/d" "$run/log.txt"
        rlAssertGrep "pending /tests/do-not/1" "$run/log.txt"
        rlAssertGrep "pending /tests/do-not/2" "$run/log.txt"

        rlAssertEquals "check expected outcomes" \
            "$(yq '[sort_by(.name) | .[] | "\(.name):\(.result)"] | join(" ")' ${run}/plan/execute/results.yaml)" \
            "/tests/do:error /tests/do-not/1:pending /tests/do-not/2:pending"

        rlAssertEquals "results should record the test aborted" \
            "$(yq '[.[] | .check[] | .name] | sort | join(" ")' ${run}/plan/execute/results.yaml)" \
            "internal/interrupt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
