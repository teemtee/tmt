#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "source fedora-version.sh"
        rlRun "pushd data"
        rlRun "run=/var/tmp/tmt/run-upgrade"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt \
            --context distro=fedora-${PREVIOUS_VERSION} \
            --context upgrade-path="${UPGRADE_PATH}" \
            run --id $run --scratch --rm -vvv --before cleanup \
            plan --name /plan/skip-tests/before" 0 "Run the upgrade test"

        # 0 test before + 3 upgrade tasks + 1 test after
        rlAssertGrep "4 tests passed" $rlRun_LOG
        rlAssertNotGrep "pass /old/test" $rlRun_LOG
        rlAssertGrep    "pass /new/test" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest
        rlRun -s "tmt \
            --context distro=fedora-${PREVIOUS_VERSION} \
            --context upgrade-path="${UPGRADE_PATH}" \
            run --id $run --scratch --rm -vvv --before cleanup \
            plan --name /plan/skip-tests/after" 0 "Run the upgrade test"

        # 1 test before + 3 upgrade tasks + 0 test after
        rlAssertGrep "4 tests passed" $rlRun_LOG
        rlAssertGrep    "pass /old/test" $rlRun_LOG
        rlAssertNotGrep "pass /new/test" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "tmt run --id $run cleanup" 0 "Stop the guest and remove the workdir"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
