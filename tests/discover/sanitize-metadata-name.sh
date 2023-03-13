#!/bin/bash

. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "workdir=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "pushd $workdir"
        rlRun "tmt init -t base --force"
    rlPhaseEnd

    rlPhaseStartTest "Sanitize plan name"
        plan_name="/plans/example"
        rlRun -s "tmt -vvv run discover plans -n $plan_name"
        rlRun -s "tmt -vvv run discover plans -n $(printf '\x1b[31m'$plan_name'\x1b[0m')" "1-255"
        rlAssertGrep "Invalid name.*$plan_name" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartTest "Sanitize test name"
        test_name="/tests/example"
        rlRun -s "tmt -vvv run discover tests -n $test_name"
        rlAssertGrep "summary: 1 test selected" $rlRun_LOG
        rlRun -s "tmt -vvv run discover tests -n $(printf '\x1b[31m'$test_name'\x1b[0m')" "1-255"
        rlAssertGrep "Invalid name.*$test_name" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -rf $workdir" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
