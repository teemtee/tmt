#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

imported="/plans/must-be-imported-and-modified"
importing="/plans/importing-other-plan-and-modify-environment"

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd modify-data"
    rlPhaseEnd

    rlPhaseStartTest "Show imported plan (invalid unless modified)"
        rlRun -s "tmt plan show ${imported}"
        rlAssertGrep 'test "${VARIABLE}" == "foobar"' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Show importing plan (modify imported plan)"
        rlRun -s "tmt plan show ${importing}"
        rlAssertGrep 'test "foobar" == "foobar"' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Run plan ${importing}"
        rlRun -s "tmt run -vv plan --name ${importing}" 0 "Run plan ${importing}"
        rlAssertGrep 'cmd: test "foobar" == "foobar"' $rlRun_LOG
        rlAssertGrep "summary: 1 test passed" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
