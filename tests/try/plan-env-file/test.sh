#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1
rlJournalStart
    rlPhaseStartSetup
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "export TMT_NO_COLOR=1"
        rlRun "pushd data"
    rlPhaseEnd

    rlPhaseStartTest "Try the plan and quit"
        rlRun -s "LANG=en_US ./start_test.exp" 0
        rlAssertGrep "My variable is good" $rlRun_LOG
        rlAssertGrep "and yours is bad" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Run the prepare step, start the test and quit"
        rlRun -s "LANG=en_US ./start_ask_test.exp" 0
        rlAssertGrep "My variable is good" $rlRun_LOG
        rlAssertGrep "and yours is bad" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Login to guest, run the test and quit"
        rlRun -s "LANG=en_US ./start_login.exp" 0
        rlAssertGrep "My variable is good" $rlRun_LOG
        rlAssertGrep "and yours is bad" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Run all the steps manually and quit"
        rlRun -s "LANG=en_US ./start_ask_manual.exp" 0
        rlAssertGrep "My variable is good" $rlRun_LOG
        rlAssertGrep "and yours is bad" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Skip the prepare step, start the test and quit"
        rlRun -s "LANG=en_US ./start_ask_test_skip.exp" 0
        rlAssertNotGrep "My variable is good" $rlRun_LOG
        rlAssertGrep "and yours is bad" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
