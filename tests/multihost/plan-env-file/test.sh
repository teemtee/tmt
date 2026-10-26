#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    rlPhaseStartTest "Check identity of variables, but uniqueness of env files"
        rlRun -s "tmt -vvv run --scratch --id $run discover provision execute finish cleanup plan -n plan"

        rlAssertEquals "Two different guests reported the TEST_MESSAGE variable" "$(grep 'stdout: TEST_MESSAGE:' $rlRun_LOG | sed 's/.*\[\(.*\)\].*/\1/' | sort -u | wc -l)" "2"
        rlAssertEquals "No empty CONST_MESSAGE values" "$(grep 'stdout: CONST_MESSAGE:' $rlRun_LOG | sed 's/.*stdout: CONST_MESSAGE: //' | grep -c '^$')" "0"
        rlAssertEquals "All guests see same CONST_MESSAGE" "$(grep 'stdout: CONST_MESSAGE:' $rlRun_LOG | sed 's/.*stdout: CONST_MESSAGE: //' | sort -u | wc -l)" "1"

        rlAssertEquals "No empty TEST_MESSAGE values" "$(grep 'stdout: TEST_MESSAGE:' $rlRun_LOG | sed 's/.*stdout: TEST_MESSAGE: //' | grep -c '^$')" "0"
        rlAssertEquals "All guests see unique TEST_MESSAGE" "$(grep 'stdout: TEST_MESSAGE:' $rlRun_LOG | sed 's/.*stdout: TEST_MESSAGE: //' | sort -u | wc -l)" "2"

        rlAssertEquals "Two different guests reported the TMT_PLAN_ENVIRONMENT_FILE variable" "$(grep 'stdout: TMT_PLAN_ENVIRONMENT_FILE:' $rlRun_LOG | sed 's/.*\[\(.*\)\].*/\1/' | sort -u | wc -l)" "2"
        rlAssertEquals "No empty TMT_PLAN_ENVIRONMENT_FILE values" "$(grep 'stdout: TMT_PLAN_ENVIRONMENT_FILE:' $rlRun_LOG | sed 's/.*stdout: TMT_PLAN_ENVIRONMENT_FILE: //' | grep -c '^$')" "0"
        rlAssertEquals "All guests see unique TMT_PLAN_ENVIRONMENT_FILE" "$(grep 'stdout: TMT_PLAN_ENVIRONMENT_FILE:' $rlRun_LOG | sed 's/.*stdout: TMT_PLAN_ENVIRONMENT_FILE: //' | sort -u | wc -l)" "2"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
