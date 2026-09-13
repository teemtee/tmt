#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-virtual}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "log=$run/log.txt"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    tmt_command="tmt run --id $run --scratch -a -vv provision -h $PROVISION_HOW test -n"

    rlPhaseStartTest "Enabled dmesg check requests /bin/dmesg with $PROVISION_HOW"
        rlRun "$tmt_command /essential-requires/enabled"
        rlAssertGrep "/bin/dmesg" "$log"
    rlPhaseEnd

    rlPhaseStartTest "Disabled dmesg check skips /bin/dmesg with $PROVISION_HOW"
        rlRun "$tmt_command /essential-requires/disabled"
        rlAssertNotGrep "/bin/dmesg" "$log"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run"
    rlPhaseEnd
rlJournalEnd
