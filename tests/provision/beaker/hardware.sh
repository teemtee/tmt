#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check hardware custom config"
        rlRun -s "TMT_CONFIG_DIR='config' tmt run --dry plan --name plan/hardware"

        rlAssertGrep '<dummyname op="==" value="dummy"/>' $rlRun_LOG
        rlAssertGrep '<key_value key="MODULE" op="==" value="ahci"/>' $rlRun_LOG
        rlAssertGrep '<key_value key="MODULE" op="==" value="uhci"/>' $rlRun_LOG
        rlAssertGrep '<key_value key="BOOTDISK" op="==" value="foo"/>' $rlRun_LOG
        rlAssertGrep '<key_value key="BOOTDISK" op="==" value="bar"/>' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
