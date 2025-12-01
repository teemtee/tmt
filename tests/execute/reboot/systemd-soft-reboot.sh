#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "set -o pipefail"
        rlRun "pushd systemd-soft-reboot"
    rlPhaseEnd

    rlPhaseStartTest "Systemd soft-reboot test"
        rlRun -s "tmt -vv run --scratch -i $run -a provision -h $PROVISION_HOW"

        rlAssertGrep "SoftRebootsCount=0" "$run/plan/execute/data/guest/default-0/test-1/data/Check-reboot-variables/output.txt"
        rlAssertGrep "SoftRebootsCount=1" "$run/plan/execute/data/guest/default-0/test-1/data/Check-reboot-variables/output.txt"
        rlAssertGrep "SoftRebootsCount=2" "$run/plan/execute/data/guest/default-0/test-1/data/Check-reboot-variables/output.txt"
        rlAssertGrep "SoftRebootsCount=3" "$run/plan/execute/data/guest/default-0/test-1/data/Check-reboot-variables/output.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf output $run" 0 "Remove run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
