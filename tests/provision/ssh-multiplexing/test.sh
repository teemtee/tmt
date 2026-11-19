#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"

        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "long_run=\$(mktemp -d /tmp/tmp.veryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryverylongXXX)" 0 "Create run directory with a very long name"

        rlRun "tmpdir=\$(mktemp -d)" 0 "Create temporary directory"
        rlRun "sed 's|RUN|$run|g' test.exp > $tmpdir/test.exp"
        rlRun "chmod a+x $tmpdir/test.exp"

        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "SSH multiplexing should be enabled by default ($PROVISION_HOW)"
        rlRun "tmt -vv run -i $run provision -h $PROVISION_HOW"
        rlAssertGrep "Spawning the SSH master process" "$run/log.txt"
    rlPhaseEnd

    rlPhaseStartTest "SSH multiplexing should be disabled when SSH socket path gets too long ($PROVISION_HOW)"
        rlRun "tmt -vv run -i $long_run -a provision -h $PROVISION_HOW"
        rlAssertGrep "warn: SSH multiplexing will not be used because the SSH master socket path '.*' is too long." "$long_run/log.txt"
        rlAssertGrep "The SSH master process cannot be terminated because it is disabled." "$long_run/log.txt"
    rlPhaseEnd

    if [ "$PROVISION_HOW" = "virtual" ]; then
        rlPhaseStartTest "Reconnect retries a failed SSH master start after reboot (#5164)"
            rlRun "run_connect=\$(mktemp -d)" 0 "Create connect run directory"
            rlRun "guest=\$(yq '.\"default-0\" | .\"primary-address\"' '$run/plan/provision/guests.yaml')" \
                0 "Read guest address"
            rlRun "guest_port=\$(yq '.\"default-0\" | .port' '$run/plan/provision/guests.yaml')" \
                0 "Read guest SSH port"
            rlRun "guest_key=\$(yq '.\"default-0\" | .key[0]' '$run/plan/provision/guests.yaml')" \
                0 "Read guest SSH key"
            rlRun "cp '$guest_key' '$tmpdir/reconnect-key'" 0 "Preserve guest SSH key"

            rlRun "tmt -vv run -i '$run' prepare -h shell --script 'mkdir -p /etc/systemd/system/sshd.service.d; printf \"[Service]\\nExecStartPre=/bin/sleep 3\\n\" > /etc/systemd/system/sshd.service.d/tmt-delay.conf; systemctl daemon-reload'" \
                0 "Delay SSH daemon startup"
            rlRun -s "ssh -oBatchMode=yes -oControlMaster=no -oControlPath=none \
                -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -oConnectTimeout=60 \
                -p '$guest_port' -i '$tmpdir/reconnect-key' root@$guest 'systemctl reboot'; \
                status=\$?; test \$status -eq 0 -o \$status -eq 255" \
                0 "Reboot guest directly"
            rlRun "sleep 1" 0 "Wait for guest reboot to begin"

            rlRun -s "TMT_SSH_CONNECTION_ATTEMPTS=1 TMT_SSH_CONNECT_TIMEOUT=1 \
                TMT_SSH_MASTER_START_TIMEOUT=1 tmt -vvv -ddd run -i '$run_connect' \
                provision -h connect --guest '$guest' --port '$guest_port' --key '$tmpdir/reconnect-key'" \
                0 "Reconnect after an initial SSH master failure"
            rlAssertGrep "waiting for condition 'try_whoami'" "$rlRun_LOG"
            rlAssertGrep "Connection timed out during banner exchange\|Connection refused" "$rlRun_LOG"
            rlAssertGrep "SSH master process .* has been terminated unexpectedly" "$rlRun_LOG"
            rlAssertGrep "'try_whoami' finished successfully" "$rlRun_LOG"
            rlRun "test \$(grep -c 'SSH master process is not running and will be spawned\\.' '$rlRun_LOG') -eq 2" \
                0 "Retry the SSH master process after the initial failure"
            rlRun "tmt run -i '$run_connect' cleanup" 0 "Clean up connect guest"
            rlRun "tmt run -i '$run' cleanup" 0 "Clean up original virtual guest"
            rlRun "rm -r '$run_connect'" 0 "Remove connect run directory"
        rlPhaseEnd

        rlPhaseStartTest "Make sure SSH multiplexing does not block reuse of guests (#3520)"
            rlRun "tmt -vv run -i $run --scratch provision -h $PROVISION_HOW"

            rlRun "pgrep --full 'ssh .* -i $run/plan/provision/default-0/id_ecdsa'" 1 "Check whether the SSH master process is still running"

            rlRun -s "$tmpdir/test.exp"
            rlAssertGrep "Starting interactive shell" $rlRun_LOG
            rlAssertGrep "Interactive shell finished" $rlRun_LOG

            rlRun "tmt -vv run -i $run finish"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmpdir" 0 "Remove temporary directory"
        rlRun "rm -r $run" 0 "Remove run directory"
        rlRun "rm -r $long_run" 0 "Remove run directory with the long name"
    rlPhaseEnd
rlJournalEnd
