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
            run --id $run --scratch -avv \
            plan --name /plan/multi-phase-discover" 0 "Run the upgrade test with multiple discover phases"

        # 2 test before + 3 upgrade tasks + 2 test after
        rlAssertGrep "7 tests passed" $rlRun_LOG

        # There should only be 1 execute task
        rlAssertGrep "execute task #1:" $rlRun_LOG
        rlAssertNotGrep "execute task #2:" $rlRun_LOG

        rlAssertEquals "system upgrade should happen only once" "$(grep -o 'upgrade: perform the system upgrade' $rlRun_LOG | wc -l)" 1

        # Check that the IN_PLACE_UPGRADE variable was set for discover phase 1 (default-0)
        rlAssertGrep "IN_PLACE_UPGRADE=old" "$run/plan/multi-phase-discover/execute/data/guest/default-0/old/default-0/test-1/output.txt"
        rlAssertGrep "IN_PLACE_UPGRADE=new" "$run/plan/multi-phase-discover/execute/data/guest/default-0/new/default-0/test-1/output.txt"

        # Check that the extra discover phase test was run before and after the upgrade
        rlAssertExists "$run/plan/multi-phase-discover/execute/data/guest/default-0/old/extra-phase/extra-test-2/output.txt"
        rlAssertExists "$run/plan/multi-phase-discover/execute/data/guest/default-0/new/extra-phase/extra-test-2/output.txt"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove the run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
