#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

imported="/plans/must-be-imported-and-modified"
importing="/plans/importing-other-plan-and-modify-environment"

rlJournalStart
    rlPhaseStartSetup
        rlRun "pushd modify-data"
    rlPhaseEnd

    rlPhaseStartTest "Show imported plan"
        rlRun -s "tmt plan show /plans/must-be-imported-and-modified"

        rlAssertGrep "environment VARIABLE: foo" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Show importing plan"
        rlRun -s "tmt plan show /importing/and-dont-modify" 0 "Show importing plan without modifications"
        rlAssertGrep "environment VARIABLE: foo" $rlRun_LOG

        rlRun -s "tmt plan show /importing/and-modify" 0 "Show importing plan with modification via fmf"
        rlAssertGrep "environment VARIABLE: bar" $rlRun_LOG

        rlRun -s "tmt plan show --environment VARIABLE=baz /importing/and-modify" 0 "Show importing plan with modification via CLI"
        rlAssertGrep "environment VARIABLE: baz" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Run plan importing plan"
        rlRun -s "tmt run -vvv plan --name /importing/and-dont-modify" 0 "Run importing plan without modifications"
        rlAssertGrep 'out: VARIABLE=foo' $rlRun_LOG

        rlRun -s "tmt run -vvv plan --name /importing/and-modify" 0 "Run importing plan with modifications via fmf"
        rlAssertGrep 'out: VARIABLE=bar' $rlRun_LOG

        rlRun -s "tmt run -vvv --environment VARIABLE=baz plan --name /importing/and-modify" 0 "Run importing plan with modifications via CLI"
        rlAssertGrep 'out: VARIABLE=baz' $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
    rlPhaseEnd
rlJournalEnd
