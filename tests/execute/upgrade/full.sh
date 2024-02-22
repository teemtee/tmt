#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "source fedora-version.sh"
        rlRun "pushd data"
        rlRun "run=/var/tmp/tmt/run-upgrade"
    rlPhaseEnd

    rlPhaseStartTest
        # Perform the full distro upgrade
        rlRun -s "tmt \
            --context distro=fedora-${PREVIOUS_VERSION} \
            --context upgrade-path="${UPGRADE_PATH}" \
            run --id $run --scratch --rm -vvv --before finish \
            plan --name /plan/path" 0 "Run the upgrade test"

        # 1 test before + 3 upgrade tasks + 1 test after
        rlAssertGrep "5 tests passed" $rlRun_LOG

        # Check that the IN_PLACE_UPGRADE variable was set
        rlAssertGrep "IN_PLACE_UPGRADE=old" "$run/plan/path/execute/data/guest/default-0/old/test-1/output.txt"
        rlAssertGrep "IN_PLACE_UPGRADE=new" "$run/plan/path/execute/data/guest/default-0/new/test-1/output.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "tmt run --id $run finish" 0 "Stop the guest and remove the workdir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
