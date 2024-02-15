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

            rlRun "tmt run -l reboot" 2 "Containers do not support soft reboot"
            rlRun -s "tmt run -l reboot --hard"
            rlAssertGrep "Reboot finished" $rlRun_LOG
            rlRun "rm $rlRun_LOG"
            rlRun "tmt run -l finish"
        rlPhaseEnd
    fi

    if [[ "$PROVISION_HOW" =~ beaker ]]; then
        rlPhaseStartTest "Beaker"
            rlRun "tmt run --scratch -i $run provision -h beaker"

            rlRun -s "tmt run -l reboot"
            rlAssertGrep "Reboot finished" $rlRun_LOG
            rlRun "rm $rlRun_LOG"

            rlRun -s "tmt run -l reboot --hard"
            rlAssertGrep "Reboot finished" $rlRun_LOG
            rlRun "rm $rlRun_LOG"

            rlRun "tmt run -l finish"
        rlPhaseEnd
    fi

    if [[ "$PROVISION_HOW" =~ virtual ]]; then
        rlPhaseStartTest "Virtual"
            rlRun "tmt run --scratch -i $run provision -h virtual"

            rlRun -s "tmt run -l reboot"
            rlAssertGrep "Reboot finished" $rlRun_LOG
            rlRun "rm $rlRun_LOG"

            rlRun -s "tmt run -l reboot --hard"
            rlAssertGrep "Reboot finished" $rlRun_LOG
            rlRun "rm $rlRun_LOG"

            rlRun "tmt run -l finish"
        rlPhaseEnd
    fi

    if [[ "$PROVISION_HOW" =~ connect ]]; then
        rlPhaseStartTest "Connect"
            rlRun "tmt run --scratch -i $run provision -h virtual"

            guest_ip="$(yq -r '."default-0" | .guest' $run/plan/provision/guests.yaml)"
            guest_port="$(yq -r '."default-0" | .port' $run/plan/provision/guests.yaml)"
            guest_key="$(yq -r '."default-0" | .key[0]' $run/plan/provision/guests.yaml)"

            provision="provision -h connect --guest $guest_ip --port $guest_port --key $guest_key"

            # Soft reboot
            rlRun -s "tmt -vv run --scratch -i $run_connect $provision reboot --step provision"
            rlAssertGrep "Reboot finished" $rlRun_LOG

            # Hard reboot
            rlRun -s "tmt -vv run --scratch -i $run_connect $provision reboot --step provision --hard" 2
            rlAssertGrep "fail: Guest 'default-0' does not support hard reboot." $rlRun_LOG

            # Custom reboot commands
            # The command is pretty what would tmt run anyway, minus the envvars
            custom_reboot="ssh -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -p $guest_port -i $guest_key root@$guest_ip reboot"

            # Soft reboot
            rlRun -s "tmt -vv run                --scratch -i $run_connect $provision --soft-reboot '$custom_reboot' reboot --step provision" 2
            rlAssertGrep "Custom soft and hard reboot commands are allowed only with the '--feeling-safe' option." $rlRun_LOG

            rlRun -s "tmt -vv --feeling-safe run --scratch -i $run_connect $provision --soft-reboot '$custom_reboot' reboot --step provision"
            rlAssertGrep "Reboot finished" $rlRun_LOG
            rlAssertGrep "cmd: /bin/bash -c '$custom_reboot'" $rlRun_LOG

            # Hard reboot
            rlRun -s "tmt -vv run                --scratch -i $run_connect $provision --hard-reboot '$custom_reboot' reboot --step provision" 2
            rlAssertGrep "Custom soft and hard reboot commands are allowed only with the '--feeling-safe' option." $rlRun_LOG

            rlRun -s "tmt -vv --feeling-safe run --scratch -i $run_connect $provision --hard-reboot '$custom_reboot' reboot --step provision --hard"
            rlAssertGrep "Reboot finished" $rlRun_LOG
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
