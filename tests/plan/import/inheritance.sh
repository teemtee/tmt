#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd inheritance"
    rlPhaseEnd

    rlPhaseStartTest "No inheritance (except command line)"
        rlRun -s "tmt plan show /no-inheritance"
        rlAssertGrep "environment\s+PROVISION_HOW: local" $rlRun_LOG -E
        rlAssertGrep "context\s+provision_how: local" $rlRun_LOG -E

        rlRun -s "tmt -c provision_how=cmd_value plan show -e PROVISION_HOW=cmd_value /no-inheritance"
        rlAssertGrep "environment\s+PROVISION_HOW: cmd_value" $rlRun_LOG -E
        rlAssertGrep "context\s+provision_how: cmd_value" $rlRun_LOG -E
    rlPhaseEnd

    rlPhaseStartTest "Inherit context"
        rlRun -s "tmt plan show /inherit-context"
        rlAssertGrep "environment\s+PROVISION_HOW: local" $rlRun_LOG -E
        rlAssertGrep "context\s+provision_how: parent_value" $rlRun_LOG -E

        rlRun -s "tmt -c provision_how=cmd_value plan show /inherit-context"
        rlAssertGrep "context\s+provision_how: cmd_value" $rlRun_LOG -E

        rlAssertNotGrep "provision_how: local" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Inherit environment"
        rlRun -s "tmt plan show /inherit-environment"
        rlAssertGrep "environment\s+PROVISION_HOW: parent_value" $rlRun_LOG -E
        rlAssertGrep "context\s+provision_how: local" $rlRun_LOG -E

        rlRun -s "tmt plan show -e PROVISION_HOW=cmd_value /inherit-environment"
        rlAssertGrep "environment\s+PROVISION_HOW: cmd_value" $rlRun_LOG -E

        rlAssertNotGrep "PROVISION_HOW: local" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Inherit all"
        rlRun -s "tmt plan show /inherit-all"
        rlAssertGrep "environment\s+PROVISION_HOW: parent_value" $rlRun_LOG -E
        rlAssertGrep "context\s+provision_how: parent_value" $rlRun_LOG -E

        rlRun -s "tmt -c provision_how=cmd_value plan show -e PROVISION_HOW=cmd_value /inherit-all"
        rlAssertGrep "environment\s+PROVISION_HOW: cmd_value" $rlRun_LOG -E
        rlAssertGrep "context\s+provision_how: cmd_value" $rlRun_LOG -E

        rlAssertNotGrep "provision_how: local" $rlRun_LOG
        rlAssertNotGrep "PROVISION_HOW: local" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
