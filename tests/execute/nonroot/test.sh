#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        # use `/var/tmp` to persist the run dir during reboots, because `bootc` package manager used
        rlRun "run=\$(mktemp -d -p /var/tmp)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest
        if ! rlRun "TMT_SHOW_TRACEBACK=full tmt run -vvvvdddd --id $run"; then
            rlFileSubmit $run/log.txt
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
