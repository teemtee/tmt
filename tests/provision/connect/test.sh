#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "run_connect=\$(mktemp -d)" 0 "Create run directory for connect plugin"
        rlRun "run_connect_no_become=\$(mktemp -d)" 0 "Create run directory for connect plugin"
        rlRun "pushd $tmp"
        rlRun "set -o pipefail"
        rlRun "tmt init"
        rlRun "tmt plan create -t mini plan"
    rlPhaseEnd

    rlPhaseStartTest "Connect with non-root user and reboot"
        # First provision a host using virtual provisioner with fedora user
        rlRun "tmt run --scratch -i $run provision -h virtual --user fedora"

        # Extract SSH login details from the provision step
        rlRun "guest_port=\$(yq -r '.\"default-0\" | .port' $run/plan/provision/guests.yaml)"
        rlRun "guest_key=\$(yq -r '.\"default-0\" | .key[0]' $run/plan/provision/guests.yaml)"
        rlRun "guest_user=\$(yq -r '.\"default-0\" | .user' $run/plan/provision/guests.yaml)"

        # Create connect provision command with become=true for reboot
        provision="provision -h connect --guest localhost --port $guest_port --key $guest_key --user $guest_user --become"

        # Test reboot with non-root user using become (should apply sudo)
        rlRun -s "tmt -vv run --scratch -i $run_connect $provision reboot --step provision"
        rlAssertGrep "Reboot finished" $rlRun_LOG
        rlAssertGrep "sudo /bin/bash -c reboot" $rlRun_LOG

        # Test reboot without become (should fail for non-root user)
        provision_no_become="provision -h connect --guest localhost --port $guest_port --key $guest_key --user $guest_user"
        rlRun -s "tmt -vv run --scratch -i $run_connect_no_become $provision_no_become reboot --step provision" 2
        rlAssertGrep "fail: Command 'reboot' returned 1." $rlRun_LOG
        rlAssertGrep "Call to Reboot failed: Interactive authentication required." $rlRun_LOG

        rlRun "tmt run -i $run cleanup"
        rlRun "tmt run -i $run_connect cleanup"
        rlRun "tmt run -i $run_connect_no_become cleanup"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
        rlRun "rm -r $run $run_connect $run_connect_no_become" 0 "Remove run directories"
    rlPhaseEnd
rlJournalEnd
