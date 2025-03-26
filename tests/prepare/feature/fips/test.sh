#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
. ../../../images.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW}"
        if [ "$PROVISION_HOW" = "container" ]; then
            CONTAINER="ubi/8/upstream:latest"
            build_container_image $CONTAINER
        fi
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Positive testing"
        if [ "$PROVISION_HOW" = "virtual" ]; then
            rlRun "tmt -vvv run -a plan --name /plans/fips/enabled provision --how virtual --image centos-stream-9"
            rlRun "tmt -vvv run -a plan --name /plans/fips/enabled provision --how virtual --image centos-stream-10"
        fi
    rlPhaseEnd

    rlPhaseStartTest "Negative testing"
        if [ "$PROVISION_HOW" = "container" ]; then
            rlRun -s "tmt -vvv run -a plan -n /plans/fips/disabled provision --how container --image $TEST_IMAGE_PREFIX/$CONTAINER" 2
            rlAssertGrep "FIPS prepare feature does not support 'disabled'." $rlRun_LOG
            rlRun -s "tmt -vvv run -a plan -n /plans/fips/enabled provision --how container --image $TEST_IMAGE_PREFIX/$CONTAINER" 2
            rlAssertGrep "FIPS prepare feature is not supported on ostree or container systems." $rlRun_LOG
        elif [ "$PROVISION_HOW" = "virtual" ]; then
            rlRun -s "tmt -vvv run -a plan --name /plans/fips/enabled provision --how virtual --image fedora-coreos" 2
            rlAssertGrep "FIPS prepare feature is not supported on ostree or container systems." $rlRun_LOG
            rlRun -s "tmt -vvv run -a plan --name /fips/enabled provision --how virtual --image fedora-rawhide" 2
            rlAssertGrep "FIPS prepare feature is supported on RHEL/CentOS-Stream 8, 9 or 10." $rlRun_LOG
        fi
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
