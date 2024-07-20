#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        # Must be outside of /tmp, reboot would remove it otherwise
        rlRun "run=\$(mktemp -d -p /var/tmp/tmt)" 0 "Create run directory"
        rlRun "pushd freeze"
    rlPhaseEnd

    rlPhaseStartTest "Guest Freeze"
        rlRun "TMT_REBOOT_TIMEOUT=10 tmt run --id $run -vvv" 2
        rlAssertGrep "foo" "$run/plan/execute/data/guest/default-0/tests/one-1/data/one.txt"
        rlAssertGrep "bar" "$run/plan/execute/data/guest/default-0/tests/two-2/data/two.txt"
        rlAssertGrep "foo" "$run/plan/data/one.txt"
        rlAssertGrep "bar" "$run/plan/data/two.txt"
    rlPhaseEnd

    rlPhaseStartTest "Check Report"
        rlRun -s "tmt run --id $run report -v" 2
        rlAssertGrep "pass /tests/one" $rlRun_LOG
        rlAssertGrep "errr /tests/two (reboot timeout)" $rlRun_LOG
        rlAssertGrep "summary: 1 test passed and 1 error" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
