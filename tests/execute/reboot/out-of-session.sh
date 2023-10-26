#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

PROVISION_METHODS=${PROVISION_METHODS:-container}

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d -p /var/tmp)" 0 "Create run directory"
        rlRun "set -o pipefail"
        rlRun "pushd out-of-session"
    rlPhaseEnd

    for method in $PROVISION_METHODS; do
        rlPhaseStartTest "Out-of-session reboot test ($method)"
            # Spawn the tmt process, in the background - tmt is expected to run the plan and test,
            # and reach a `sleep 3600`.
            tmt run -e TMT_DEBUG=1 --scratch -i $run -dddvvva provision -h $method execute -h tmt $interactive &> tmt.output &
            tmt_pid="$!"

            rlLogInfo "Running \"tmt run -e TMT_DEBUG=1 --scratch -i $run -dddvvva provision -h $method execute -h tmt $interactive &> tmt.output\" in the background"
            rlLogInfo "Background tmt PID is $tmt_pid"

            # Now we wait for the test to go to sleep...
            while true; do
                rlLogInfo "checking output for 'sleep 3600'..."

                current_tail="$(tail -n 10 tmt.output)"

                if [[ "$current_tail" == *"Running 'sleep 3600'"* ]]; then
                    rlLogInfo "found!"
                    break;
                fi

                sleep 10
            done

            rlLogInfo "tmt output, before reboot:"
            rlLogInfo "$(cat tmt.output)"

            # When the test is sleeping, we can extract the podman command & container ID from tmt log,
            # and use it to issue a `tmt-reboot` from outside the direct process tree of the test.
            set -x

            tmt_reboot_command="export TMT_TEST_PIDFILE=/var/tmp/tmt-test.pid; export TMT_TEST_PIDFILE_LOCK=/var/tmp/tmt-test.pid.lock; export TMT_DEBUG=1; tmt-reboot"

            if [ "$method" = "container" ]; then
                podman_exec="$(sed -nr 's/\s*Run command: (podman exec .*) \/bin\/bash.*cd.*/\1/p' tmt.output)"

                $podman_exec bash -c "$tmt_reboot_command"

            elif [ "$method" = "virtual" ]; then
                ssh_exec="$(sed -nr "s/\s*Run command: (ssh .* -tt root@.*) 'export .*/\1/p" tmt.output)"

                $ssh_exec "$tmt_reboot_command"
            fi

            set +x

            # Reboot has been issued, wait for tmt to finish: the test should be interrupted, restarted,
            # and finish successfully.
            wait "$tmt_pid"

            rlLogInfo "tmt output. full:"
            rlLogInfo "$(cat tmt.output)"

            rlAssertGrep "TMT_REBOOT_COUNT=0" tmt.output
            rlAssertGrep "Before reboot" tmt.output
            rlAssertGrep "Running 'sleep 3600'" tmt.output

            rlAssertGrep "TMT_REBOOT_COUNT=1" tmt.output
            rlAssertGrep "After first reboot" tmt.output

            rlAssertGrep "OVERALL RESULT: PASS" tmt.output
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "rm -rf tmt.output $run" 0 "Remove run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
