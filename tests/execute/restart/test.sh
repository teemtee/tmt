#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "WITH_REBOOT=${WITH_REBOOT:-no}"
        rlRun "run=\$(mktemp -d -p /var/tmp)" 0 "Create run directory"
        rlRun "set -o pipefail"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Run a test that requests a restart ($PROVISION_HOW)"
        if [ "$WITH_REBOOT" = "yes" ]; then
            rlRun -s "tmt -vv run --scratch -i $run -a provision -h $PROVISION_HOW test -n /with-reboot"
            rlRun "inner_test=$run/plan/execute/data/guest/default-0/test/with-reboot-1/output.txt"
        else
            rlRun -s "tmt -vv run --scratch -i $run -a provision -h $PROVISION_HOW test -n /basic"
            rlRun "inner_test=$run/plan/execute/data/guest/default-0/test/basic-1/output.txt"
        fi

        rlLogInfo "Inner test output:"
        rlLogInfo "$(cat $inner_test)"

        if [ "$WITH_REBOOT" != "yes" ]; then
            rlAssertGrep "TMT_REBOOT_COUNT=0" $inner_test
            rlAssertGrep "TMT_TEST_RESTART_COUNT=0" $inner_test

            rlAssertNotGrep "TMT_REBOOT_COUNT=1" $inner_test
            rlAssertGrep    "TMT_TEST_RESTART_COUNT=1" $inner_test

            rlAssertNotGrep "TMT_REBOOT_COUNT=2" $inner_test
            rlAssertGrep    "TMT_TEST_RESTART_COUNT=2" $inner_test
        else
            rlAssertGrep "TMT_REBOOT_COUNT=0" $inner_test
            rlAssertGrep "TMT_TEST_RESTART_COUNT=0" $inner_test

            rlAssertGrep "TMT_REBOOT_COUNT=1" $inner_test
            rlAssertGrep "TMT_TEST_RESTART_COUNT=1" $inner_test

            rlAssertGrep "TMT_REBOOT_COUNT=2" $inner_test
            rlAssertGrep "TMT_TEST_RESTART_COUNT=2" $inner_test
        fi

        rlAssertNotGrep "TMT_REBOOT_COUNT=3" $inner_test
        rlAssertNotGrep "TMT_TEST_RESTART_COUNT=3" $inner_test

        rlAssertNotGrep "TMT_REBOOT_COUNT=4" $inner_test
        rlAssertNotGrep "TMT_TEST_RESTART_COUNT=4" $inner_test

        rlAssertNotGrep "TMT_REBOOT_COUNT=5" $inner_test
        rlAssertNotGrep "TMT_TEST_RESTART_COUNT=5" $inner_test
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "rm -rf $run" 0 "Remove run directory"
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
