#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "PROVISION_HOW=${PROVISION_HOW:-local}"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Custom Script"
        rlRun "tmt run -arv provision --how=$PROVISION_HOW plan -n custom" 0 "Prepare using a custom script"
    rlPhaseEnd

    rlPhaseStartTest "Commandline Script"
        rlRun "tmt run -arv provision --how=$PROVISION_HOW plan -n custom \
            prepare -h shell -s './prepare.sh'" 0 "Prepare using a custom script from cmdline"
    rlPhaseEnd

    rlPhaseStartTest "Multiple Commandline Scripts"
        rlRun "tmt run -arv provision --how=$PROVISION_HOW plans -n multiple \
            prepare -h shell -s 'touch /tmp/first' -s 'touch /tmp/second'"
    rlPhaseEnd

    rlPhaseStartTest "Remote Script"
        rlRun -s "tmt -vvv run provision --how=$PROVISION_HOW prepare finish cleanup plan -n url" 0 "Prepare using a remote script"
        rlAssertGrep "Hello world" "$rlRun_LOG" #check for the prepare script
        rlAssertGrep "third" "$rlRun_LOG" # check for the finish script
    rlPhaseEnd

    rlPhaseStartTest "Reboot"
        rlRun -s "tmt -vvv run -a provision --how=$PROVISION_HOW plan -n '/reboot'"

        rlAssertGrep "out: TMT_REBOOT_COUNT=0" $rlRun_LOG
        rlAssertGrep "out: RSTRNT_REBOOTCOUNT=0" $rlRun_LOG
        rlAssertGrep "out: REBOOTCOUNT=0" $rlRun_LOG
        rlAssertGrep "out: Before reboot: TMT_REBOOT_COUNT=0" $rlRun_LOG
        rlAssertGrep "out: Trigger one then!" $rlRun_LOG
        rlAssertGrep "out: TMT_REBOOT_COUNT=1" $rlRun_LOG
        rlAssertGrep "out: RSTRNT_REBOOTCOUNT=1" $rlRun_LOG
        rlAssertGrep "out: REBOOTCOUNT=1" $rlRun_LOG
        rlAssertGrep "out: After reboot: TMT_REBOOT_COUNT=1" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
