#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "pushd data"
        rlRun "set -o pipefail"
    rlPhaseEnd

    tmt_command="tmt run -vv --scratch --id ${run} plan --name"

    planName="/plan/good"
    rlPhaseStartTest "Execution finishes successfully"
        rlRun -s "${tmt_command} ${planName} 2>&1 >/dev/null" 1 "Warning is expected"
        rlAssertGrep "info /test/info" $rlRun_LOG
        rlAssertGrep "warn /test/warn" $rlRun_LOG
        rlAssertGrep "pass /test/pass" $rlRun_LOG
        rlAssertGrep "pass /test/another-pass" $rlRun_LOG
        rlAssertNotGrep "fail: Test .* stopping execution." $rlRun_LOG
        rlAssertGrep "summary: 4 tests executed" $rlRun_LOG
        rlAssertGrep "total: 2 tests passed, 1 info and 1 warn" $rlRun_LOG
    rlPhaseEnd

    planName="/plan/fail"
    rlPhaseStartTest "Execution stops after the first failure"
        rlRun -s "${tmt_command} ${planName} 2>&1 >/dev/null" 1 "Failure is expected"
        rlAssertGrep "pass /test/pass" $rlRun_LOG
        rlAssertGrep "fail /test/fail" $rlRun_LOG
        rlAssertNotGrep "pass /test/another-pass" $rlRun_LOG
        rlAssertGrep "fail: Test /test/fail failed, stopping execution." $rlRun_LOG
        rlAssertGrep "summary: 2 tests executed" $rlRun_LOG
        rlAssertGrep "total: 1 test passed, 1 test failed and 1 pending" $rlRun_LOG
    rlPhaseEnd

    planName="/plan/error"
    rlPhaseStartTest "Execution stops after the first error"
        rlRun -s "${tmt_command} ${planName} 2>&1 >/dev/null" 2 "Error is expected"
        rlAssertGrep "pass /test/pass" $rlRun_LOG
        rlAssertGrep "errr /test/error" $rlRun_LOG
        rlAssertNotGrep "pass /test/another-pass" $rlRun_LOG
        rlAssertGrep "fail: Test /test/error failed, stopping execution." $rlRun_LOG
        rlAssertGrep "summary: 2 tests executed" $rlRun_LOG
        rlAssertGrep "total: 1 test passed, 1 error and 1 pending" $rlRun_LOG
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $run" 0 "Remove run directory"
    rlPhaseEnd
rlJournalEnd
