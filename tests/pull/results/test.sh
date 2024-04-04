#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Test $PROVISION_HOW"
        # Run the plan, check for expected results
        rlRun -s "tmt run -av --scratch --id $run provision -h $PROVISION_HOW" 1
        rlAssertGrep "2 tests passed and 1 test failed" $rlRun_LOG

        # Check output and extra logs in the test data directory
        data="$run/plan/execute/data"
        rlAssertGrep "ok" "$data/guest/default-0/test/good-3/output.txt"
        rlAssertGrep "ko" "$data/guest/default-0/test/bad-1/output.txt"
        rlAssertGrep "extra good" "$data/guest/default-0/test/good-3/data/extra.log"
        rlAssertGrep "extra bad" "$data/guest/default-0/test/bad-1/data/extra.log"

        # Check logs in the plan data directory
        rlAssertGrep "common good" "$run/plan/data/log.txt"
        rlAssertGrep "common bad" "$run/plan/data/log.txt"

        # Check report of the last run for correct results
        rlRun -s "tmt run --last report" 1
        rlAssertGrep "2 tests passed and 1 test failed" $rlRun_LOG

        # Check beakerlib's backup directory pull
        if [[ "$PROVISION_HOW" =~ local|container ]]; then
            # No pull happened so it should be present
            rlAssertExists "$data/guest/default-0/test/beakerlib-2/backup"
            rlAssertExists "$data/guest/default-0/test/beakerlib-2/backup-NS1"
            rlAssertNotEquals "any backup dir is present" "$(eval 'echo $data/guest/default-0/test/beakerlib-2/backup*')" "$data/guest/default-0/test/beakerlib-2/backup*"
        else
            # Should be ignored
            rlAssertNotExists "$data/guest/default-0/test/beakerlib-2/backup"
            rlAssertNotExists "$data/guest/default-0/test/beakerlib-2/backup-NS1"
            rlAssertEquals "no backup dir is present" "$(eval 'echo $data/guest/default-0/test/beakerlib-2/backup*')" "$data/guest/default-0/test/beakerlib-2/backup*"
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
