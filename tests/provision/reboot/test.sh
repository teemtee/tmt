#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-container}"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "run_connect=\$(mktemp -d)" 0 "Create run directory for connect plugin"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init"
        rlRun "tmt plan create -t mini plan"
    rlPhaseEnd

    if [[ "$PROVISION_HOW" =~ container ]]; then
        rlPhaseStartTest "Container"
            rlRun "tmt run -i $run provision -h container"

            # - Soft reboot -----------------------------------------------------------------------
            rlRun -s "tmt -vv run -l reboot --soft" \
                2 "Soft reboot"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "Guest 'default-0' does not support soft reboot. Containers can only be stopped and started again (hard reboot)." $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --soft --command 'reboot'" \
                2 "Soft reboot with custom command"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "Custom reboot command not supported in podman provision." $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --soft --command 'dummy'" \
                2 "Soft reboot with invalid custom command"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "Custom reboot command not supported in podman provision." $rlRun_LOG

            # - Systemd soft-reboot----------------------------------------------------------------
            rlRun -s "tmt -vv run -l reboot --systemd-soft" \
                2 "Systemd soft-reboot"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "Guest 'default-0' does not support systemd-soft reboot. Containers can only be stopped and started again (hard reboot)." $rlRun_LOG

            # - Hard reboot -----------------------------------------------------------------------
            rlRun -s "tmt -vv run -l reboot --hard" \
                0 "Hard reboot"
            rlAssertGrep "reboot: Rebooting guest using hard mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG

            rlRun "tmt run -l finish"
        rlPhaseEnd
    fi

    if [[ "$PROVISION_HOW" =~ beaker ]]; then
        rlPhaseStartTest "Beaker"
            rlRun "tmt run --scratch -i $run provision -h beaker"

            # Soft reboot
            rlRun -s "tmt -vv run -l reboot" \
                0 "Soft reboot"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --command 'reboot'" \
                0 "Soft reboot with custom command"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: reboot" $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --command 'dummy'" \
                2 "Soft reboot with invalid custom command"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "dummy: command not found" $rlRun_LOG

            # Systemd soft-reboot
            rlRun -s "tmt -vv run -l reboot --systemd-soft" \
                0 "Systemd soft-reboot"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: systemctl soft-reboot" $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --systemd-soft --command 'systemctl soft-reboot'" \
                0 "Systemd soft-reboot with custom command"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: systemctl soft-reboot" $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --systemd-soft --command 'dummy'" \
                2 "Systemd soft-reboot with invalid custom command"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "dummy: command not found" $rlRun_LOG

            # Hard reboot
            rlRun -s "tmt -vv run -l reboot --hard" \
                0 "Hard reboot"
            rlAssertGrep "reboot: Rebooting guest using hard mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG

            rlRun "tmt run -l finish"
        rlPhaseEnd
    fi

    if [[ "$PROVISION_HOW" =~ virtual ]]; then
        rlPhaseStartTest "Virtual"
            rlRun "tmt run --scratch -i $run provision -h virtual"

            # Soft reboot
            rlRun -s "tmt -vv run -l reboot" \
                0 "Soft reboot"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --command 'reboot'" \
                0 "Soft reboot with custom command"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: reboot" $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --command 'dummy'" \
                2 "Soft reboot with invalid custom command"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "dummy: command not found" $rlRun_LOG

            # Systemd soft-reboot
            rlRun -s "tmt -vv run -l reboot --systemd-soft" \
                0 "Systemd soft-reboot"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: systemctl soft-reboot" $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --systemd-soft --command 'systemctl soft-reboot'" \
                0 "Systemd soft-reboot with custom command"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: systemctl soft-reboot" $rlRun_LOG

            rlRun -s "tmt -vv run -l reboot --systemd-soft --command 'dummy'" \
                2 "Systemd soft-reboot with invalid custom command"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "dummy: command not found" $rlRun_LOG

            # Hard reboot
            rlRun -s "tmt -vv run -l reboot --hard" \
                0 "Hard reboot"
            rlAssertGrep "reboot: Rebooting guest using hard mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG

            rlRun "tmt run -l finish"
        rlPhaseEnd
    fi

    if [[ "$PROVISION_HOW" =~ connect ]]; then
        rlPhaseStartTest "Connect"
            rlRun "tmt run --scratch -i $run provision -h virtual"

            guest_ip="$(yq '."default-0" | ."primary-address"' $run/plan/provision/guests.yaml)"
            guest_port="$(yq '."default-0" | .port' $run/plan/provision/guests.yaml)"
            guest_key="$(yq '."default-0" | .key[0]' $run/plan/provision/guests.yaml)"

            provision="provision -h connect --guest $guest_ip --port $guest_port --key $guest_key"
            # Custom reboot command - the command is pretty what would tmt run anyway, minus the envvars
            custom_reboot="ssh -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -p $guest_port -i $guest_key root@$guest_ip reboot"

            # - Soft reboot -----------------------------------------------------------------------
            rlRun -s "tmt -vv run                --scratch -i $run_connect $provision                                reboot --step provision" \
                0 "Soft reboot"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG

            rlRun -s "tmt -vv run                --scratch -i $run_connect $provision                                reboot --step provision --command reboot" \
                0 "Soft reboot with custom command"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: reboot" $rlRun_LOG

            rlRun -s "tmt -vv run                --scratch -i $run_connect $provision --soft-reboot '$custom_reboot' reboot --step provision" \
                2 "Soft reboot with custom soft-reboot command"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "Custom soft and hard reboot commands are allowed only with the '--feeling-safe' option." $rlRun_LOG

            rlRun -s "tmt -vv --feeling-safe run --scratch -i $run_connect $provision --soft-reboot '$custom_reboot' reboot --step provision" \
                0 "Soft reboot with custom soft-reboot command and --feeling-safe"
            rlAssertGrep "reboot: Rebooting guest using soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: /bin/bash -c '$custom_reboot'" $rlRun_LOG

            # - Systemd soft-reboot ---------------------------------------------------------------
            rlRun -s "tmt -vv run --scratch -i $run_connect $provision reboot --systemd-soft --step provision" \
                0 "Systemd soft-reboot"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: systemctl soft-reboot" "$run_connect/log.txt"

            rlRun -s "tmt -vv run --scratch -i $run_connect $provision reboot --systemd-soft --command 'systemctl soft-reboot' --step provision" \
                0 "Systemd soft-reboot with custom command"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: systemctl soft-reboot" "$run_connect/log.txt"

            rlRun -s "tmt -vvv run --scratch -i $run_connect $provision reboot --systemd-soft --command 'dummy' --step provision" \
                2 "systemd soft-reboot with invalid custom command"
            rlAssertGrep "reboot: Rebooting guest using systemd-soft mode." $rlRun_LOG
            rlAssertGrep "dummy: command not found" $rlRun_LOG

            # - Hard reboot -----------------------------------------------------------------------
            rlRun -s "tmt -vv                run --scratch -i $run_connect $provision                                reboot --step provision --hard" \
                2 "Hard reboot"
            rlAssertGrep "reboot: Rebooting guest using hard mode." $rlRun_LOG
            rlAssertGrep "fail: Guest 'default-0' does not support hard reboot." $rlRun_LOG

            rlRun -s "tmt -vv run                --scratch -i $run_connect $provision --hard-reboot '$custom_reboot' reboot --step provision --hard" \
                2 "Hard reboot with custom hard-reboot command"
            rlAssertGrep "reboot: Rebooting guest using hard mode." $rlRun_LOG
            rlAssertGrep "Custom soft and hard reboot commands are allowed only with the '--feeling-safe' option." $rlRun_LOG

            rlRun -s "tmt -vv --feeling-safe run --scratch -i $run_connect $provision --hard-reboot '$custom_reboot' reboot --step provision --hard" \
                0 "Hard reboot with custom hard-reboot command and --feeling-safe"
            rlAssertGrep "reboot: Rebooting guest using hard mode." $rlRun_LOG
            rlAssertGrep "reboot: Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: /bin/bash -c '$custom_reboot'" $rlRun_LOG

            rlRun "tmt run -i $run finish"
        rlPhaseEnd
    fi

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $run $run_connect" 0 "Remove run directories"
    rlPhaseEnd
rlJournalEnd
rlJournalPrintText
